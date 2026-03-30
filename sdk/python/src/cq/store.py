"""Local SQLite knowledge store for cq.

Stores knowledge units in a SQLite database following the XDG Base Directory
spec. Default location: $XDG_DATA_HOME/cq/local.db (~/.local/share/cq/local.db).
Auto-creates the database directory and schema on first use.
Implements the context manager protocol for deterministic resource cleanup.
"""

import logging
import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

from pydantic import BaseModel, Field

from .models import KnowledgeUnit
from .scoring import calculate_relevance

logger = logging.getLogger(__name__)

# Sort fallback for knowledge units with no last_confirmed timestamp.
_EPOCH_UTC = datetime.min.replace(tzinfo=UTC)

# Confidence distribution bucket boundaries (upper bound, label).
_CONFIDENCE_BUCKETS: list[tuple[float, str]] = [
    (0.3, "0.0-0.3"),
    (0.5, "0.3-0.5"),
    (0.7, "0.5-0.7"),
    (float("inf"), "0.7-1.0"),
]


def _default_db_path() -> Path:
    """Return the default database path per the XDG Base Directory spec."""
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg and Path(xdg).is_absolute():
        return Path(xdg) / "cq" / "local.db"
    if xdg:
        logger.warning(
            "Ignoring non-absolute XDG_DATA_HOME=%r; falling back to default.",
            xdg,
        )
    return Path.home() / ".local" / "share" / "cq" / "local.db"


class StoreStats(BaseModel):
    """Aggregated statistics for the local knowledge store."""

    total_count: int
    domain_counts: dict[str, int] = Field(default_factory=dict)
    recent: list[KnowledgeUnit] = Field(default_factory=list)
    confidence_distribution: dict[str, int] = Field(default_factory=dict)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_units (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_unit_domains (
    unit_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    FOREIGN KEY (unit_id) REFERENCES knowledge_units(id) ON DELETE CASCADE,
    PRIMARY KEY (unit_id, domain)
);

CREATE INDEX IF NOT EXISTS idx_domains_domain
    ON knowledge_unit_domains(domain);
"""

_FTS_SCHEMA_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_units_fts
    USING fts5(id UNINDEXED, summary, detail, action);
"""

_METADATA_SQL = """
CREATE TABLE IF NOT EXISTS metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _normalize_domains(domains: list[str]) -> list[str]:
    """Lowercase, strip whitespace, drop empties, and deduplicate domain tags."""
    return list(dict.fromkeys(d.strip().lower() for d in domains if d.strip()))


_FTS_MAX_TERMS = 20
_MAX_QUERY_DOMAINS = 50
_FTS_MAX_TERM_LENGTH = 200


def _build_fts_match_expr(terms: list[str]) -> str:
    r"""Build a safe FTS5 MATCH expression from untrusted search terms.

    FTS5 MATCH accepts a mini query language where double quotes delimit
    phrase queries. Characters like /, \\, \*, +, -, ^, etc. are all
    harmless *inside* a quoted phrase. The only character that can break
    a quoted phrase is an unescaped double quote.

    This function strips double quotes from each term, truncates to
    ``_FTS_MAX_TERM_LENGTH`` characters, wraps each surviving term in
    double quotes, and joins with OR. At most ``_FTS_MAX_TERMS`` terms
    are included. Returns an empty string when no usable terms remain.

    The result is intended for use as the value of a parameterised
    ``MATCH ?`` query, never for string interpolation into SQL.
    """
    safe: list[str] = []
    for term in terms:
        cleaned = term.replace('"', "").strip()[:_FTS_MAX_TERM_LENGTH]
        if cleaned:
            safe.append(f'"{cleaned}"')
        if len(safe) >= _FTS_MAX_TERMS:
            break
    return " OR ".join(safe)


class LocalStore:
    """SQLite-backed local knowledge store.

    Holds a single persistent connection for the lifetime of the instance.
    Use as a context manager or call ``close()`` explicitly.

    Thread-safe: a lock serializes all connection access so the store
    can be shared across asyncio.to_thread() executor threads.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize the store, creating the database and schema if needed.

        Args:
            db_path: Path to the SQLite database file.
                     Defaults to $XDG_DATA_HOME/cq/local.db.
        """
        if db_path is None:
            db_path = _default_db_path()
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._closed = False
        self._conn = self._open_connection()
        self._ensure_schema()

    def _open_connection(self) -> sqlite3.Connection:
        """Open and configure a SQLite connection."""
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        fk_enabled = conn.execute("PRAGMA foreign_keys").fetchone()
        if not fk_enabled or fk_enabled[0] != 1:
            raise RuntimeError("SQLite foreign key enforcement is not available")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _ensure_schema(self) -> None:
        """Create tables, indexes, FTS virtual table, and metadata if needed."""
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.executescript(_FTS_SCHEMA_SQL)
        self._conn.executescript(_METADATA_SQL)
        self._stamp_writer()

    def _stamp_writer(self) -> None:
        """Record this SDK as the last writer for cross-SDK diagnostics."""
        import importlib.metadata
        import sys

        try:
            pkg_version = importlib.metadata.version("cq-sdk")
        except importlib.metadata.PackageNotFoundError:
            pkg_version = "dev"
        tag = f"cq-python/{pkg_version} python/{sys.version.split()[0]}"
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("last_writer", tag),
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("last_write_at", now),
        )
        self._conn.commit()

    def _check_open(self) -> None:
        """Raise if the store has been closed."""
        if self._closed:
            raise RuntimeError("LocalStore is closed")

    def close(self) -> None:
        """Close the underlying database connection."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._conn.close()

    def __enter__(self) -> "LocalStore":
        """Enter the context manager."""
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        """Exit the context manager, closing the connection."""
        self.close()

    @property
    def db_path(self) -> Path:
        """Path to the SQLite database file."""
        return self._db_path

    def insert(self, unit: KnowledgeUnit) -> None:
        """Insert a knowledge unit into the store.

        Raises:
            sqlite3.IntegrityError: If a unit with the same ID already exists.
            ValueError: If domain normalization results in no valid domains.
        """
        domains = _normalize_domains(unit.domains)
        if not domains:
            raise ValueError("At least one non-empty domain is required")
        unit = unit.model_copy(update={"domains": domains})
        data = unit.model_dump_json()
        with self._lock:
            self._check_open()
            with self._conn:
                self._conn.execute(
                    "INSERT INTO knowledge_units (id, data) VALUES (?, ?)",
                    (unit.id, data),
                )
                self._conn.executemany(
                    "INSERT INTO knowledge_unit_domains (unit_id, domain) VALUES (?, ?)",
                    [(unit.id, d) for d in domains],
                )
                fts_sql = "INSERT INTO knowledge_units_fts (id, summary, detail, action) VALUES (?, ?, ?, ?)"
                self._conn.execute(
                    fts_sql,
                    (unit.id, unit.insight.summary, unit.insight.detail, unit.insight.action),
                )

    def get(self, unit_id: str) -> KnowledgeUnit | None:
        """Retrieve a knowledge unit by ID, or None if not found."""
        with self._lock:
            self._check_open()
            row = self._conn.execute(
                "SELECT data FROM knowledge_units WHERE id = ?",
                (unit_id,),
            ).fetchone()
        if row is None:
            return None
        return KnowledgeUnit.model_validate_json(row[0])

    def all(self) -> list[KnowledgeUnit]:
        """Return every knowledge unit in the store."""
        with self._lock:
            self._check_open()
            rows = self._conn.execute("SELECT data FROM knowledge_units").fetchall()
        return [KnowledgeUnit.model_validate_json(row[0]) for row in rows]

    def delete(self, unit_id: str) -> None:
        """Remove a knowledge unit by ID.

        Raises:
            KeyError: If no unit with the given ID exists.
        """
        with self._lock:
            self._check_open()
            with self._conn:
                # Delete FTS first (virtual tables have no CASCADE).
                # Domain rows are handled by ON DELETE CASCADE.
                self._conn.execute(
                    "DELETE FROM knowledge_units_fts WHERE id = ?",
                    (unit_id,),
                )
                cursor = self._conn.execute(
                    "DELETE FROM knowledge_units WHERE id = ?",
                    (unit_id,),
                )
                if cursor.rowcount == 0:
                    raise KeyError(f"Knowledge unit not found: {unit_id}")

    def update(self, unit: KnowledgeUnit) -> None:
        """Replace an existing knowledge unit in the store.

        Raises:
            KeyError: If no unit with the given ID exists.
            ValueError: If domain normalization results in no valid domains.
        """
        domains = _normalize_domains(unit.domains)
        if not domains:
            raise ValueError("At least one non-empty domain is required")
        unit = unit.model_copy(update={"domains": domains})
        data = unit.model_dump_json()
        with self._lock:
            self._check_open()
            with self._conn:
                cursor = self._conn.execute(
                    "UPDATE knowledge_units SET data = ? WHERE id = ?",
                    (data, unit.id),
                )
                if cursor.rowcount == 0:
                    raise KeyError(f"Knowledge unit not found: {unit.id}")
                self._conn.execute(
                    "DELETE FROM knowledge_unit_domains WHERE unit_id = ?",
                    (unit.id,),
                )
                self._conn.executemany(
                    "INSERT INTO knowledge_unit_domains (unit_id, domain) VALUES (?, ?)",
                    [(unit.id, d) for d in domains],
                )
                self._conn.execute(
                    "DELETE FROM knowledge_units_fts WHERE id = ?",
                    (unit.id,),
                )
                fts_sql = "INSERT INTO knowledge_units_fts (id, summary, detail, action) VALUES (?, ?, ?, ?)"
                self._conn.execute(
                    fts_sql,
                    (unit.id, unit.insight.summary, unit.insight.detail, unit.insight.action),
                )

    def query(
        self,
        domains: list[str],
        *,
        language: str | None = None,
        framework: str | None = None,
        limit: int = 5,
    ) -> list[KnowledgeUnit]:
        """Search for knowledge units by domain tags with relevance ranking.

        Retrieves units whose domain tags overlap with the query, then
        adds additional candidates from the FTS5 full-text index (these
        may have no domain overlap). All candidates are scored, optionally
        boosted by language or framework context, and ranked by
        relevance * confidence.

        Raises:
            ValueError: If limit is not positive.
        """
        if limit <= 0:
            raise ValueError("limit must be positive")
        if not domains:
            return []

        normalized = _normalize_domains(domains)
        if not normalized:
            return []
        if len(normalized) > _MAX_QUERY_DOMAINS:
            logger.warning(
                "Query domain count (%d) exceeds limit (%d); truncating.",
                len(normalized),
                _MAX_QUERY_DOMAINS,
            )
            normalized = normalized[:_MAX_QUERY_DOMAINS]

        # Safe: placeholders is only '?' characters, never user input.
        placeholders = ",".join("?" for _ in normalized)
        sql = f"""
            SELECT ku.data
            FROM knowledge_units ku
            WHERE ku.id IN (
                SELECT DISTINCT unit_id
                FROM knowledge_unit_domains
                WHERE domain IN ({placeholders})
            )
        """
        fts_terms = _build_fts_match_expr(normalized)
        fts_sql = """
            SELECT ku.data
            FROM knowledge_units_fts fts
            JOIN knowledge_units ku ON ku.id = fts.id
            WHERE knowledge_units_fts MATCH ?
        """
        with self._lock:
            self._check_open()
            rows = self._conn.execute(sql, normalized).fetchall()
            fts_rows: list[tuple[Any, ...]] = []
            if fts_terms:
                try:
                    fts_rows = self._conn.execute(fts_sql, (fts_terms,)).fetchall()
                except sqlite3.OperationalError:
                    logger.warning(
                        "FTS query failed (expression length=%d chars)",
                        len(fts_terms),
                        exc_info=True,
                    )

        # Merge and deduplicate by ID.
        seen: set[str] = set()
        units: list[KnowledgeUnit] = []
        for row in [*rows, *fts_rows]:
            unit = KnowledgeUnit.model_validate_json(row[0])
            if unit.id not in seen:
                seen.add(unit.id)
                units.append(unit)

        scored = []
        for unit in units:
            relevance = calculate_relevance(
                unit,
                normalized,
                query_language=language,
                query_framework=framework,
            )
            scored.append((relevance * unit.evidence.confidence, unit))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [unit for _, unit in scored[:limit]]

    def stats(self, *, recent_limit: int = 5) -> StoreStats:
        """Return aggregated statistics for the local store.

        Raises:
            ValueError: If recent_limit is negative.
        """
        if recent_limit < 0:
            raise ValueError("recent_limit must be non-negative")

        with self._lock:
            self._check_open()
            total = self._conn.execute("SELECT COUNT(*) FROM knowledge_units").fetchone()[0]
            domain_rows = self._conn.execute(
                "SELECT domain, COUNT(*) AS cnt FROM knowledge_unit_domains GROUP BY domain ORDER BY cnt DESC"
            ).fetchall()
            all_rows = self._conn.execute("SELECT data FROM knowledge_units").fetchall()

        domain_counts = {row[0]: row[1] for row in domain_rows}
        units = [KnowledgeUnit.model_validate_json(row[0]) for row in all_rows]

        units.sort(
            key=lambda u: u.evidence.last_confirmed or _EPOCH_UTC,
            reverse=True,
        )
        recent = units[:recent_limit]

        buckets = {label: 0 for _, label in _CONFIDENCE_BUCKETS}
        for unit in units:
            c = unit.evidence.confidence
            label = next(lb for t, lb in _CONFIDENCE_BUCKETS if c < t)
            buckets[label] += 1

        return StoreStats(
            total_count=total,
            domain_counts=domain_counts,
            recent=recent,
            confidence_distribution=buckets,
        )
