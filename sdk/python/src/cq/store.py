"""Local persistence for cq: the Store SPI and its SQLite default.

The ``Store`` Protocol is the narrow contract the Client depends on; the
default ``SqliteStore`` implements it over SQLite following the XDG Base
Directory spec. Default location: $XDG_DATA_HOME/cq/local.db
(~/.local/share/cq/local.db). The store auto-creates the database
directory and schema on first use and implements the context manager
protocol for deterministic resource cleanup.

``create_store`` resolves a connection-string URL to a concrete store, and
``rank_candidates`` is the shared ranker any implementation can reuse so a
from-scratch store only has to gather candidates and hand them over.
"""

import logging
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from .models import KnowledgeUnit, Tier
from .scoring import calculate_relevance

logger = logging.getLogger(__name__)

# Sort fallback for knowledge units with no last_confirmed timestamp.
_EPOCH_UTC = datetime.min.replace(tzinfo=UTC)

# Confidence-distribution buckets (exclusive upper bound, label), ordered low
# to high. These labels are the canonical wire-contract convention; servers and
# other SDKs follow the same labels so a remote distribution merges without the
# labels drifting apart.
_CONFIDENCE_BUCKETS: list[tuple[float, str]] = [
    (0.3, "0.0-0.3"),
    (0.5, "0.3-0.5"),
    (0.7, "0.5-0.7"),
    (float("inf"), "0.7-1.0"),
]

_FTS_MAX_TERMS = 20
_FTS_MAX_TERM_LENGTH = 200

# Store-level query bounds, aligned with the Go SDK.
_MAX_QUERY_DOMAINS = 50
_MAX_QUERY_FRAMEWORKS = 50
_MAX_QUERY_LANGUAGES = 50
_MAX_QUERY_LIMIT = 500


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


class DuplicateUnitError(Exception):
    """Raised when inserting a knowledge unit whose ID already exists.

    A backend-neutral error so the Client and any store implementation
    agree on duplicate-insert semantics regardless of the underlying
    storage engine.
    NOTE: implementations must map their driver's uniqueness violation
    onto this error so callers never see a driver-specific exception.
    """


class StoreStats(BaseModel):
    """Aggregated statistics for the knowledge store."""

    total_count: int
    domain_counts: dict[str, int] = Field(default_factory=dict)
    # Most recently added units from the local store.
    recent: list[KnowledgeUnit] = Field(default_factory=list)
    # Covers the local store plus any private/org units a configured remote
    # reports; it excludes the public commons. Keyed by the canonical bucket
    # labels (see _CONFIDENCE_BUCKETS).
    confidence_distribution: dict[str, int] = Field(default_factory=dict)
    # Keyed by Tier rather than str: the tiers are a closed set, and typing
    # the keys keeps producers and consumers from drifting into bare strings.
    tier_counts: dict[Tier, int] = Field(default_factory=dict)

    # Non-fatal issues encountered while aggregating stats, such as a
    # remote API being unreachable. When present, the reported counts
    # reflect the local store only.
    warnings: list[str] = Field(default_factory=list)


# Default number of ranked results when a query does not request a positive limit.
_DEFAULT_QUERY_LIMIT = 5


class QueryParams(BaseModel):
    """Inputs to a store query: domain tags plus optional ranking context.

    A frozen value object passed at the Store SPI boundary in place of
    keyword arguments. Domains drive candidate selection; languages,
    frameworks, and pattern are secondary ranking signals; limit caps the
    returned units. Normalization (lowercasing, deduplication, truncation)
    is the store's responsibility, applied inside ``query``.
    """

    model_config = ConfigDict(frozen=True)

    domains: list[str]
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    pattern: str = ""
    limit: int = _DEFAULT_QUERY_LIMIT


class StoreQueryResult(BaseModel):
    """Ranked query output plus any non-fatal degradation warnings.

    ``units`` is ordered most-relevant first. ``warnings`` is the single
    channel for non-fatal degradation (for example a full-text index that
    could not be consulted for a given query); it is empty on a clean run.
    """

    units: list[KnowledgeUnit] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


@runtime_checkable
class Store(Protocol):
    """Local persistence provider for the cq SDK.

    Runtime-checkable Protocol; the default SqliteStore and first-party
    adapters satisfy it structurally. The Client depends only on these
    methods and never learns whether a store uses full-text search, what
    dialect it speaks, or how it ranks.
    NOTE: implementations must be safe for use across asyncio.to_thread
    executor threads.
    """

    def get(self, unit_id: str) -> KnowledgeUnit | None:
        """Retrieve a knowledge unit by ID, or None if not found."""
        ...

    def all(self) -> list[KnowledgeUnit]:
        """Return every knowledge unit in the store."""
        ...

    def insert(self, unit: KnowledgeUnit) -> None:
        """Insert a knowledge unit; raise DuplicateUnitError on an existing ID."""
        ...

    def update(self, unit: KnowledgeUnit) -> None:
        """Replace an existing knowledge unit; raise KeyError when absent."""
        ...

    def delete(self, unit_id: str) -> None:
        """Remove a knowledge unit by ID; raise KeyError when absent."""
        ...

    def query(self, params: QueryParams) -> StoreQueryResult:
        """Return units matching the query, ranked most-relevant first."""
        ...

    def stats(self, *, recent_limit: int = 5) -> StoreStats:
        """Return aggregated statistics for the store."""
        ...

    def close(self) -> None:
        """Release any resources the store holds."""
        ...


def _normalize_domains(domains: list[str]) -> list[str]:
    """Lowercase, strip whitespace, drop empties, and deduplicate domain tags."""
    return list(dict.fromkeys(d.strip().lower() for d in domains if d.strip()))


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


def create_store(database_url: str | None = None) -> Store:
    """Resolve a connection-string URL to a concrete Store.

    A ``None`` URL or a ``sqlite:`` URL selects the built-in SqliteStore.
    Accepted SQLite forms are ``sqlite:///<path>`` (absolute) and
    ``sqlite:<path>``; the path is taken verbatim.
    A ``postgresql://`` or ``postgres://`` URL selects PostgresStore when
    the ``cq-sdk[postgres]`` extra is installed.
    Any other scheme raises ValueError.

    Args:
        database_url: The store connection string, or None for the
            zero-config SQLite default at the XDG path.

    Returns:
        A Store ready for use.

    Raises:
        NotImplementedError: For a PostgreSQL URL when psycopg is not
            installed.
        ValueError: For an unrecognized scheme.
    """
    if database_url is None:
        return SqliteStore()

    if database_url.startswith("sqlite:///"):
        path = database_url[len("sqlite:///") :]
        if not path:
            raise ValueError("sqlite store URL must include a file path")
        return SqliteStore(db_path=Path(path))
    if database_url.startswith("sqlite:"):
        path = database_url[len("sqlite:") :]
        if not path:
            raise ValueError("sqlite store URL must include a file path")
        return SqliteStore(db_path=Path(path))
    if database_url.startswith(("postgresql://", "postgres://")):
        try:
            from .stores.postgres import PostgresStore
        except ModuleNotFoundError as exc:
            if exc.name is None or not exc.name.startswith("psycopg"):
                raise
            raise NotImplementedError(
                "PostgreSQL support requires psycopg; install the 'cq-sdk[postgres]' extra."
            ) from exc
        return PostgresStore(database_url)
    raise ValueError("Unsupported database URL scheme; expected sqlite: or postgresql:")


def rank_candidates(candidates: list[KnowledgeUnit], params: QueryParams) -> list[KnowledgeUnit]:
    """Rank candidate units by relevance * confidence and truncate to the limit.

    The shared ranker every Store implementation reuses: a store gathers
    candidates however it likes (domain tags, full-text, native search),
    hands them here, and returns the result. Scoring multiplies each
    unit's relevance (domain overlap plus language/framework/pattern
    boosts) by its confidence, sorts descending, and keeps the top
    ``params.limit`` units. A zero limit defaults to ``_DEFAULT_QUERY_LIMIT``.
    NOTE: callers must validate that limit is non-negative before calling;
    this helper does not reject negative values (it treats them as zero).
    """
    scored: list[tuple[float, KnowledgeUnit]] = []
    for unit in candidates:
        relevance = calculate_relevance(
            unit,
            params.domains,
            query_languages=params.languages or None,
            query_frameworks=params.frameworks or None,
            query_pattern=params.pattern,
        )
        scored.append((relevance * unit.evidence.confidence, unit))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    # A non-positive limit means "unset": fall back to the default count.
    limit = params.limit if params.limit > 0 else _DEFAULT_QUERY_LIMIT
    return [unit for _, unit in scored[:limit]]


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


class SqliteStore:
    """SQLite-backed local knowledge store; the default Store implementation.

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
            raise RuntimeError("Foreign key enforcement is not available")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _ensure_schema(self) -> None:
        """Create tables, indexes, FTS virtual table, and metadata if needed."""
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.executescript(_FTS_SCHEMA_SQL)
        self._conn.executescript(_METADATA_SQL)
        with self._conn:
            self._stamp_writer()

    def _stamp_writer(self) -> None:
        """Record this SDK as the last writer for cross-SDK diagnostics.

        NOTE: callers must ensure this runs inside a transaction (either an
        explicit ``with self._conn:`` block or as part of an existing one).
        """
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

    def _check_open(self) -> None:
        """Raise if the store has been closed."""
        if self._closed:
            raise RuntimeError("store is closed")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """Hold the connection lock for the block and assert the store is open.

        NOTE: self._lock is a non-reentrant threading.Lock, so this must
        not be entered while the current thread already holds the lock
        (including from within _transact, which builds on it) or the thread
        will self-deadlock.
        """
        with self._lock:
            self._check_open()
            yield

    @contextmanager
    def _transact(self) -> Iterator[sqlite3.Connection]:
        """Run a write transaction under the connection lock, yielding the connection.

        Composes _locked() with the connection's own transaction context:
        the body commits on success and rolls back on exception, and the
        lock is released either way. The lock is acquired exactly once, via
        _locked().
        NOTE: self._lock is non-reentrant; do not nest _transact() or
        _locked() inside the yielded block.
        """
        with self._locked(), self._conn:
            yield self._conn

    def close(self) -> None:
        """Close the underlying database connection."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._conn.close()

    def __enter__(self) -> "SqliteStore":
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
            DuplicateUnitError: If a unit with the same ID already exists.
            ValueError: If domain normalization results in no valid domains.
        """
        domains = _normalize_domains(unit.domains)
        if not domains:
            raise ValueError("At least one non-empty domain is required")
        unit = unit.model_copy(update={"domains": domains})
        data = unit.model_dump_json(exclude_none=True)
        try:
            with self._transact() as conn:
                conn.execute(
                    "INSERT INTO knowledge_units (id, data) VALUES (?, ?)",
                    (unit.id, data),
                )
                conn.executemany(
                    "INSERT INTO knowledge_unit_domains (unit_id, domain) VALUES (?, ?)",
                    [(unit.id, d) for d in domains],
                )
                fts_sql = "INSERT INTO knowledge_units_fts (id, summary, detail, action) VALUES (?, ?, ?, ?)"
                conn.execute(
                    fts_sql,
                    (unit.id, unit.insight.summary, unit.insight.detail, unit.insight.action),
                )
                self._stamp_writer()
        except sqlite3.IntegrityError as exc:
            raise DuplicateUnitError(f"Knowledge unit already exists: {unit.id}") from exc

    def get(self, unit_id: str) -> KnowledgeUnit | None:
        """Retrieve a knowledge unit by ID, or None if not found."""
        with self._locked():
            row = self._conn.execute(
                "SELECT data FROM knowledge_units WHERE id = ?",
                (unit_id,),
            ).fetchone()
        if row is None:
            return None
        return KnowledgeUnit.model_validate_json(row[0])

    def all(self) -> list[KnowledgeUnit]:
        """Return every knowledge unit in the store."""
        with self._locked():
            rows = self._conn.execute("SELECT data FROM knowledge_units").fetchall()
        return [KnowledgeUnit.model_validate_json(row[0]) for row in rows]

    def delete(self, unit_id: str) -> None:
        """Remove a knowledge unit by ID.

        Raises:
            KeyError: If no unit with the given ID exists.
        """
        with self._transact() as conn:
            # Delete FTS first (virtual tables have no CASCADE).
            # Domain rows are handled by ON DELETE CASCADE.
            conn.execute(
                "DELETE FROM knowledge_units_fts WHERE id = ?",
                (unit_id,),
            )
            cursor = conn.execute(
                "DELETE FROM knowledge_units WHERE id = ?",
                (unit_id,),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Knowledge unit not found: {unit_id}")
            self._stamp_writer()

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
        data = unit.model_dump_json(exclude_none=True)
        with self._transact() as conn:
            cursor = conn.execute(
                "UPDATE knowledge_units SET data = ? WHERE id = ?",
                (data, unit.id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Knowledge unit not found: {unit.id}")
            conn.execute(
                "DELETE FROM knowledge_unit_domains WHERE unit_id = ?",
                (unit.id,),
            )
            conn.executemany(
                "INSERT INTO knowledge_unit_domains (unit_id, domain) VALUES (?, ?)",
                [(unit.id, d) for d in domains],
            )
            conn.execute(
                "DELETE FROM knowledge_units_fts WHERE id = ?",
                (unit.id,),
            )
            fts_sql = "INSERT INTO knowledge_units_fts (id, summary, detail, action) VALUES (?, ?, ?, ?)"
            conn.execute(
                fts_sql,
                (unit.id, unit.insight.summary, unit.insight.detail, unit.insight.action),
            )
            self._stamp_writer()

    def query(self, params: QueryParams) -> StoreQueryResult:
        """Search for knowledge units by domain tags with relevance ranking.

        Retrieves units whose domain tags overlap with the query, then
        adds additional candidates from the FTS5 full-text index (these
        may have no domain overlap). All candidates are scored, optionally
        boosted by language, framework, or pattern context, and ranked by
        relevance * confidence.

        A full-text degradation is non-fatal and surfaced in
        ``StoreQueryResult.warnings`` rather than raised.

        Raises:
            ValueError: If limit is negative, exceeds the maximum, or
                language/framework counts exceed their bounds.
        """
        if params.limit < 0:
            raise ValueError("limit must be positive")
        if params.limit > _MAX_QUERY_LIMIT:
            raise ValueError(f"limit must be at most {_MAX_QUERY_LIMIT}")

        normalized = _normalize_domains(params.domains)
        if not normalized:
            return StoreQueryResult()
        if len(normalized) > _MAX_QUERY_DOMAINS:
            logger.warning(
                "Query domain count (%d) exceeds limit (%d); truncating.",
                len(normalized),
                _MAX_QUERY_DOMAINS,
            )
            normalized = normalized[:_MAX_QUERY_DOMAINS]

        languages = _normalize_domains(params.languages)
        if len(languages) > _MAX_QUERY_LANGUAGES:
            raise ValueError(f"maximum number of languages ({_MAX_QUERY_LANGUAGES}) exceeded")

        frameworks = _normalize_domains(params.frameworks)
        if len(frameworks) > _MAX_QUERY_FRAMEWORKS:
            raise ValueError(f"maximum number of frameworks ({_MAX_QUERY_FRAMEWORKS}) exceeded")

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
        warnings: list[str] = []
        with self._locked():
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
                    warnings.append("Full-text search degraded; results limited to domain matches")

        # Merge and deduplicate by ID.
        seen: set[str] = set()
        candidates: list[KnowledgeUnit] = []
        for row in [*rows, *fts_rows]:
            unit = KnowledgeUnit.model_validate_json(row[0])
            if unit.id not in seen:
                seen.add(unit.id)
                candidates.append(unit)

        ranked = rank_candidates(
            candidates,
            params.model_copy(update={"domains": normalized, "languages": languages, "frameworks": frameworks}),
        )
        return StoreQueryResult(units=ranked, warnings=warnings)

    def stats(self, *, recent_limit: int = 5) -> StoreStats:
        """Return aggregated statistics for the local store.

        Raises:
            ValueError: If recent_limit is negative.
        """
        if recent_limit < 0:
            raise ValueError("recent_limit must be non-negative")

        with self._locked():
            total = self._conn.execute("SELECT COUNT(*) FROM knowledge_units").fetchone()[0]
            domain_rows = self._conn.execute(
                "SELECT domain, COUNT(*) AS cnt FROM knowledge_unit_domains GROUP BY domain ORDER BY cnt DESC"
            ).fetchall()
            recent_rows = self._conn.execute(
                "SELECT data FROM knowledge_units ORDER BY rowid DESC LIMIT ?",
                (recent_limit,),
            ).fetchall()
            all_rows = self._conn.execute("SELECT data FROM knowledge_units").fetchall()

        domain_counts = {row[0]: row[1] for row in domain_rows}
        recent = [KnowledgeUnit.model_validate_json(row[0]) for row in recent_rows]
        units = [KnowledgeUnit.model_validate_json(row[0]) for row in all_rows]

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
            tier_counts={Tier.LOCAL: total},
        )


# Backwards-compatible alias for the pre-SPI store name. New code should
# depend on the Store Protocol and construct SqliteStore (or create_store).
LocalStore = SqliteStore
