"""PostgreSQL-backed Store implementation for the cq SDK.

Requires the ``psycopg`` driver, available via the ``cq-sdk[postgres]``
extra. Uses domain-tag candidate selection and the shared ranker; full-text
search is not yet implemented (the SPI degrades gracefully).
"""

import sys
import threading
from datetime import UTC, datetime
from typing import Any, LiteralString

import psycopg
import psycopg.sql
from psycopg.rows import tuple_row

from ..models import KnowledgeUnit, Tier
from ..store import (
    _CONFIDENCE_BUCKETS,
    _MAX_QUERY_DOMAINS,
    _MAX_QUERY_FRAMEWORKS,
    _MAX_QUERY_LANGUAGES,
    _MAX_QUERY_LIMIT,
    DuplicateUnitError,
    QueryParams,
    StoreQueryResult,
    StoreStats,
    _normalize_domains,
    rank_candidates,
)

_KEY_LAST_WRITE_AT = "last_write_at"
_KEY_LAST_WRITER = "last_writer"
_WRITER_TAG_FMT = "cq-python-sdk/postgres python/{}.{}.{}"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_units (
    rowid BIGINT GENERATED ALWAYS AS IDENTITY,
    id TEXT PRIMARY KEY,
    data JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_unit_domains (
    unit_id TEXT NOT NULL REFERENCES knowledge_units(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    PRIMARY KEY (unit_id, domain)
);

CREATE INDEX IF NOT EXISTS idx_domains_domain
    ON knowledge_unit_domains(domain);

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_SQL_DELETE_DOMAINS = "DELETE FROM knowledge_unit_domains WHERE unit_id = %s"
_SQL_DELETE_UNIT = "DELETE FROM knowledge_units WHERE id = %s"
_SQL_DOMAIN_COUNTS = "SELECT domain, COUNT(*) FROM knowledge_unit_domains GROUP BY domain ORDER BY COUNT(*) DESC"
_SQL_INSERT_DOMAIN = "INSERT INTO knowledge_unit_domains (unit_id, domain) VALUES (%s, %s)"
_SQL_INSERT_UNIT = "INSERT INTO knowledge_units (id, data) VALUES (%s, %s::jsonb)"
_SQL_SELECT_ALL = "SELECT data FROM knowledge_units"
_SQL_SELECT_BY_ID = "SELECT data FROM knowledge_units WHERE id = %s"
_SQL_SELECT_COUNT = "SELECT COUNT(*) FROM knowledge_units"
_SQL_SELECT_RECENT = "SELECT data FROM knowledge_units ORDER BY rowid DESC LIMIT %s"
_SQL_UPDATE_UNIT = "UPDATE knowledge_units SET data = %s::jsonb WHERE id = %s"

_SQL_QUERY_BY_DOMAINS = """
    SELECT DISTINCT k.data
    FROM knowledge_units k
    JOIN knowledge_unit_domains d ON k.id = d.unit_id
    WHERE d.domain = ANY(%s)
"""

_SQL_UPSERT_METADATA = """
    INSERT INTO metadata (key, value) VALUES (%s, %s)
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
"""


class PostgresStore:
    """PostgreSQL-backed Store for shared multi-agent knowledge.

    Thread-safe: a lock serializes all access so the store can be shared
    across asyncio.to_thread() executor threads.
    """

    def __init__(self, conninfo: str) -> None:
        """Connect, verify reachability, and ensure the schema exists.

        Args:
            conninfo: A PostgreSQL connection string (DSN or URL).

        Raises:
            ValueError: If conninfo is empty.
            psycopg.OperationalError: If the server is unreachable.
        """
        if not conninfo or not conninfo.strip():
            raise ValueError("connection string must not be empty")
        self._lock = threading.Lock()
        self._closed = False
        self._conn = psycopg.connect(conninfo, row_factory=tuple_row, autocommit=True)
        self._ensure_schema()

    def get(self, unit_id: str) -> KnowledgeUnit | None:
        """Retrieve a knowledge unit by ID, or None if not found."""
        with self._lock:
            self._check_open()
            row = self._conn.execute(_SQL_SELECT_BY_ID, (unit_id,)).fetchone()
        if row is None:
            return None
        return KnowledgeUnit.model_validate(row[0])

    def all(self) -> list[KnowledgeUnit]:
        """Return every knowledge unit in the store."""
        with self._lock:
            self._check_open()
            return self._scan_units(_SQL_SELECT_ALL)

    def insert(self, unit: KnowledgeUnit) -> None:
        """Insert a knowledge unit.

        Domains are normalized before storage.

        Raises:
            DuplicateUnitError: If a unit with the same ID already exists.
            ValueError: If domain normalization results in no valid domains.
        """
        domains = _normalize_domains(unit.domains)
        if not domains:
            raise ValueError("At least one non-empty domain is required")
        unit = unit.model_copy(update={"domains": domains})
        data = unit.model_dump_json(exclude_none=True)
        with self._lock:
            self._check_open()
            try:
                with self._conn.transaction():
                    self._conn.execute(_SQL_INSERT_UNIT, (unit.id, data))
                    self._insert_domains(unit.id, domains)
            except psycopg.errors.UniqueViolation as exc:
                raise DuplicateUnitError(f"Knowledge unit already exists: {unit.id}") from exc

    def update(self, unit: KnowledgeUnit) -> None:
        """Replace an existing knowledge unit.

        Domains are re-normalized and the domain index is rebuilt.

        Raises:
            KeyError: If no unit with the given ID exists.
            ValueError: If domain normalization results in no valid domains.
        """
        domains = _normalize_domains(unit.domains)
        if not domains:
            raise ValueError("At least one non-empty domain is required")
        unit = unit.model_copy(update={"domains": domains})
        data = unit.model_dump_json(exclude_none=True)
        with self._lock:
            self._check_open()
            with self._conn.transaction():
                cur = self._conn.execute(_SQL_UPDATE_UNIT, (data, unit.id))
                if cur.rowcount == 0:
                    raise KeyError(f"Knowledge unit not found: {unit.id}")
                self._conn.execute(_SQL_DELETE_DOMAINS, (unit.id,))
                self._insert_domains(unit.id, domains)

    def delete(self, unit_id: str) -> None:
        """Remove a knowledge unit by ID.

        Raises:
            KeyError: If no unit with the given ID exists.
        """
        with self._lock:
            self._check_open()
            cur = self._conn.execute(_SQL_DELETE_UNIT, (unit_id,))
            if cur.rowcount == 0:
                raise KeyError(f"Knowledge unit not found: {unit_id}")

    def query(self, params: QueryParams) -> StoreQueryResult:
        """Search for knowledge units by domain tags with relevance ranking.

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
            normalized = normalized[:_MAX_QUERY_DOMAINS]

        languages = _normalize_domains(params.languages)
        if len(languages) > _MAX_QUERY_LANGUAGES:
            raise ValueError(f"maximum number of languages ({_MAX_QUERY_LANGUAGES}) exceeded")

        frameworks = _normalize_domains(params.frameworks)
        if len(frameworks) > _MAX_QUERY_FRAMEWORKS:
            raise ValueError(f"maximum number of frameworks ({_MAX_QUERY_FRAMEWORKS}) exceeded")

        with self._lock:
            self._check_open()
            candidates = self._scan_units(_SQL_QUERY_BY_DOMAINS, (normalized,))

        ranked = rank_candidates(
            candidates,
            params.model_copy(
                update={
                    "domains": normalized,
                    "languages": languages,
                    "frameworks": frameworks,
                }
            ),
        )
        return StoreQueryResult(units=ranked)

    def stats(self, *, recent_limit: int = 5) -> StoreStats:
        """Return aggregated statistics for the store.

        Raises:
            ValueError: If recent_limit is negative.
        """
        if recent_limit < 0:
            raise ValueError("recent_limit must be non-negative")

        with self._lock:
            self._check_open()
            total = self._count_units()
            domain_counts = self._query_domain_counts()
            recent = self._scan_units(_SQL_SELECT_RECENT, (recent_limit,))
            buckets = self._compute_confidence_buckets()

        return StoreStats(
            total_count=total,
            domain_counts=domain_counts,
            recent=recent,
            confidence_distribution=buckets,
            tier_counts={Tier.LOCAL: total},
        )

    def close(self) -> None:
        """Close the database connection. Safe to call more than once."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._conn.close()

    def __enter__(self) -> "PostgresStore":
        """Support use as a context manager."""
        return self

    def __exit__(self, *_: Any) -> None:
        """Close the store on context exit."""
        self.close()

    def _check_open(self) -> None:
        """Raise RuntimeError if the store has been closed."""
        if self._closed:
            raise RuntimeError("store is closed")

    def _compute_confidence_buckets(self) -> dict[str, int]:
        """Distribute all units across the canonical confidence buckets."""
        units = self._scan_units(_SQL_SELECT_ALL)
        buckets: dict[str, int] = {label: 0 for _, label in _CONFIDENCE_BUCKETS}
        for unit in units:
            c = unit.evidence.confidence
            for threshold, label in _CONFIDENCE_BUCKETS:
                if c >= threshold:
                    continue
                buckets[label] += 1
                break
        return buckets

    def _count_units(self) -> int:
        """Return the total number of knowledge units in the store."""
        row = self._conn.execute(_SQL_SELECT_COUNT).fetchone()
        return row[0] if row is not None else 0

    def _ensure_schema(self) -> None:
        """Create tables and indexes if they do not exist, then stamp the writer."""
        self._conn.execute(_SCHEMA_SQL)
        self._stamp_writer()

    def _insert_domains(self, unit_id: str, domains: list[str]) -> None:
        """Write domain tag rows for a unit."""
        with self._conn.cursor() as cur:
            cur.executemany(_SQL_INSERT_DOMAIN, [(unit_id, d) for d in domains])

    def _query_domain_counts(self) -> dict[str, int]:
        """Return the number of knowledge units per domain tag."""
        rows = self._conn.execute(_SQL_DOMAIN_COUNTS).fetchall()
        return {row[0]: row[1] for row in rows}

    def _scan_units(self, sql: LiteralString, params: tuple[Any, ...] | None = None) -> list[KnowledgeUnit]:
        """Execute a query returning a JSONB data column and deserialize the rows."""
        query = psycopg.sql.SQL(sql)
        if params is not None:
            rows = self._conn.execute(query, params).fetchall()
        else:
            rows = self._conn.execute(query).fetchall()
        return [KnowledgeUnit.model_validate(row[0]) for row in rows]

    def _stamp_writer(self) -> None:
        """Record the SDK version and timestamp in the metadata table."""
        vi = sys.version_info
        tag = _WRITER_TAG_FMT.format(vi.major, vi.minor, vi.micro)
        now = datetime.now(UTC).isoformat()
        with self._conn.cursor() as cur:
            cur.execute(_SQL_UPSERT_METADATA, (_KEY_LAST_WRITER, tag))
            cur.execute(_SQL_UPSERT_METADATA, (_KEY_LAST_WRITE_AT, now))
