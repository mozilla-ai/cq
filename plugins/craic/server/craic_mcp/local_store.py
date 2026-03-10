"""Local SQLite knowledge store for CRAIC.

Stores knowledge units in a SQLite database at ~/.craic/local.db.
Auto-creates the database directory and schema on first use.
Implements the context manager protocol for deterministic resource cleanup.
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from pydantic import BaseModel, Field

from .knowledge_unit import KnowledgeUnit
from .scoring import calculate_relevance

# Sort fallback for knowledge units with no last_confirmed timestamp.
_EPOCH_UTC = datetime.min.replace(tzinfo=UTC)

# Confidence distribution bucket boundaries (upper bound, label).
_CONFIDENCE_BUCKETS: list[tuple[float, str]] = [
    (0.3, "0.0-0.3"),
    (0.5, "0.3-0.5"),
    (0.7, "0.5-0.7"),
    (float("inf"), "0.7-1.0"),
]

DEFAULT_DB_PATH = Path.home() / ".craic" / "local.db"


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


def _normalise_domains(domains: list[str]) -> list[str]:
    """Lowercase, strip whitespace, drop empties, and deduplicate domain tags."""
    return list(dict.fromkeys(d.strip().lower() for d in domains if d.strip()))


class LocalStore:
    """SQLite-backed local knowledge store.

    Holds a single persistent connection for the lifetime of the instance.
    Use as a context manager or call ``close()`` explicitly.

    Not thread-safe — each thread should create its own instance.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialise the store, creating the database and schema if needed.

        Args:
            db_path: Path to the SQLite database file. Defaults to ~/.craic/local.db.
        """
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._closed = False
        self._conn = self._open_connection()
        self._ensure_schema()

    def _open_connection(self) -> sqlite3.Connection:
        """Open and configure a SQLite connection."""
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _ensure_schema(self) -> None:
        """Create tables and indexes if they do not exist."""
        self._conn.executescript(_SCHEMA_SQL)

    def _check_open(self) -> None:
        """Raise if the store has been closed."""
        if self._closed:
            raise RuntimeError("LocalStore is closed")

    def close(self) -> None:
        """Close the underlying database connection."""
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

        Args:
            unit: The knowledge unit to insert.

        Raises:
            sqlite3.IntegrityError: If a unit with the same ID already exists.
            ValueError: If domain normalisation results in no valid domains.
        """
        self._check_open()
        domains = _normalise_domains(unit.domain)
        if not domains:
            raise ValueError("At least one non-empty domain is required")
        unit = unit.model_copy(update={"domain": domains})
        data = unit.model_dump_json()
        with self._conn:
            self._conn.execute(
                "INSERT INTO knowledge_units (id, data) VALUES (?, ?)",
                (unit.id, data),
            )
            self._conn.executemany(
                "INSERT INTO knowledge_unit_domains (unit_id, domain) VALUES (?, ?)",
                [(unit.id, d) for d in domains],
            )

    def get(self, unit_id: str) -> KnowledgeUnit | None:
        """Retrieve a knowledge unit by ID.

        Args:
            unit_id: The knowledge unit identifier.

        Returns:
            The knowledge unit, or None if not found.
        """
        self._check_open()
        row = self._conn.execute(
            "SELECT data FROM knowledge_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
        if row is None:
            return None
        return KnowledgeUnit.model_validate_json(row[0])

    def update(self, unit: KnowledgeUnit) -> None:
        """Replace an existing knowledge unit in the store.

        Args:
            unit: The updated knowledge unit.

        Raises:
            KeyError: If no unit with the given ID exists.
            ValueError: If domain normalisation results in no valid domains.
        """
        self._check_open()
        domains = _normalise_domains(unit.domain)
        if not domains:
            raise ValueError("At least one non-empty domain is required")
        unit = unit.model_copy(update={"domain": domains})
        data = unit.model_dump_json()
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

    def query(
        self,
        domains: list[str],
        *,
        language: str | None = None,
        framework: str | None = None,
        limit: int = 5,
    ) -> list[KnowledgeUnit]:
        """Search for knowledge units by domain tags with relevance ranking.

        Finds units with at least one overlapping domain tag, optionally
        filters by language or framework context, then ranks results by
        relevance * confidence.

        Args:
            domains: Domain tags to search for.
            language: Optional programming language filter.
            framework: Optional framework filter.
            limit: Maximum number of results to return. Must be positive.

        Returns:
            Knowledge units ranked by relevance * confidence, descending.

        Raises:
            ValueError: If limit is not positive.
        """
        self._check_open()
        if limit <= 0:
            raise ValueError("limit must be positive")
        if not domains:
            return []

        normalised = _normalise_domains(domains)
        if not normalised:
            return []
        # Safe: placeholders is only '?' characters, never user input.
        placeholders = ",".join("?" for _ in normalised)
        sql = f"""
            SELECT ku.data
            FROM knowledge_units ku
            WHERE ku.id IN (
                SELECT DISTINCT unit_id
                FROM knowledge_unit_domains
                WHERE domain IN ({placeholders})
            )
        """
        rows = self._conn.execute(sql, normalised).fetchall()

        # PoC: all filtering and scoring is in-memory after deserialization.
        # For larger stores, push coarse filters into SQL.
        units = [KnowledgeUnit.model_validate_json(row[0]) for row in rows]

        if language:
            units = [u for u in units if language in u.context.languages]
        if framework:
            units = [u for u in units if framework in u.context.frameworks]

        scored = []
        for unit in units:
            relevance = calculate_relevance(
                unit,
                normalised,
                query_language=language,
                query_framework=framework,
            )
            scored.append((relevance * unit.evidence.confidence, unit))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [unit for _, unit in scored[:limit]]

    def stats(self, *, recent_limit: int = 5) -> StoreStats:
        """Return aggregated statistics for the local store.

        Args:
            recent_limit: Maximum number of recent additions to include.

        Returns:
            Store statistics including total count, domain breakdown,
            most recent additions, and confidence distribution.

        Raises:
            ValueError: If recent_limit is negative.
        """
        self._check_open()
        if recent_limit < 0:
            raise ValueError("recent_limit must be non-negative")

        total = self._conn.execute("SELECT COUNT(*) FROM knowledge_units").fetchone()[0]

        domain_rows = self._conn.execute(
            "SELECT domain, COUNT(*) AS cnt FROM knowledge_unit_domains GROUP BY domain ORDER BY cnt DESC"
        ).fetchall()
        domain_counts = {row[0]: row[1] for row in domain_rows}

        all_rows = self._conn.execute("SELECT data FROM knowledge_units").fetchall()
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
