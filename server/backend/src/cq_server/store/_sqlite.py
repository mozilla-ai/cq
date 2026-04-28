"""SqliteStore: SQLite-backed implementation of the async Store protocol.

Async surface implemented as a threadpool shim over a sync SQLAlchemy Core
engine. SQLite-native concerns (PRAGMAs, single-writer behaviour) live here;
portable SQL is sourced from ``cq_server.store._queries``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cq.models import KnowledgeUnit
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from ..scoring import calculate_relevance
from ..tables import ensure_api_keys_table, ensure_review_columns, ensure_users_table
from ._normalize import normalize_domains
from ._queries import (
    DELETE_UNIT_DOMAINS,
    INSERT_UNIT,
    INSERT_UNIT_DOMAIN,
    SELECT_APPROVED_BY_ID,
    SELECT_BY_ID,
    SELECT_COUNTS_BY_STATUS,
    SELECT_COUNTS_BY_TIER,
    SELECT_DOMAIN_COUNTS,
    SELECT_QUERY_UNITS,
    SELECT_REVIEW_STATUS_BY_ID,
    SELECT_TOTAL_COUNT,
    UPDATE_REVIEW_STATUS,
    UPDATE_UNIT_DATA,
)

DEFAULT_DB_PATH = Path("/data/cq.db")

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


def _apply_sqlite_pragmas(dbapi_connection, _connection_record):  # noqa: ANN001  (sqlalchemy event signature)
    """Issue cq's required SQLite PRAGMAs on every new connection.

    Invoked by SQLAlchemy's ``connect`` event so the pool's per-thread
    connections all receive the same pragmas. ``executescript`` is avoided to
    keep each pragma in its own statement (SQLite docs: some pragmas only
    take effect outside a transaction).
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.execute("PRAGMA busy_timeout = 5000")
    finally:
        cursor.close()


class SqliteStore:
    """SQLite-backed Store implementation. See module docstring."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._closed = False
        self._engine: Engine = create_engine(
            f"sqlite:///{self._db_path}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        event.listen(self._engine, "connect", _apply_sqlite_pragmas)
        with self._engine.begin() as conn:
            for stmt in filter(None, (s.strip() for s in _SCHEMA_SQL.split(";"))):
                conn.exec_driver_sql(stmt)
            raw = conn.connection.driver_connection  # underlying sqlite3.Connection.
            assert raw is not None  # active engine connection always has a DBAPI connection.
            ensure_review_columns(raw)
            ensure_users_table(raw)
            ensure_api_keys_table(raw)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await asyncio.to_thread(self._engine.dispose)

    async def _run_sync(self, fn, /, *args, **kwargs):
        """Run a sync callable on the default executor and await its result.

        All public async methods funnel SQL work through this shim so the
        sqlite3 driver's blocking calls don't tie up the event-loop thread.
        Kept narrow: a single helper, no per-call allocation of executors.
        """
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def insert(self, unit: KnowledgeUnit) -> None:
        await self._run_sync(self._insert_sync, unit)

    def _insert_sync(self, unit: KnowledgeUnit) -> None:
        if self._closed:
            raise RuntimeError("SqliteStore is closed")
        domains = normalize_domains(unit.domains)
        if not domains:
            raise ValueError("knowledge unit must have at least one domain")
        created_at = datetime.now(UTC).isoformat()
        with self._engine.begin() as conn:
            conn.execute(
                INSERT_UNIT,
                {
                    "id": unit.id,
                    "data": unit.model_dump_json(),
                    "created_at": created_at,
                    "tier": unit.tier.value,
                },
            )
            for d in domains:
                conn.execute(INSERT_UNIT_DOMAIN, {"unit_id": unit.id, "domain": d})

    async def get(self, unit_id: str) -> KnowledgeUnit | None:
        return await self._run_sync(self._get_sync, unit_id)

    def _get_sync(self, unit_id: str) -> KnowledgeUnit | None:
        if self._closed:
            raise RuntimeError("SqliteStore is closed")
        with self._engine.connect() as conn:
            row = conn.execute(SELECT_APPROVED_BY_ID, {"id": unit_id}).fetchone()
        return KnowledgeUnit.model_validate_json(row[0]) if row is not None else None

    async def get_any(self, unit_id: str) -> KnowledgeUnit | None:
        return await self._run_sync(self._get_any_sync, unit_id)

    def _get_any_sync(self, unit_id: str) -> KnowledgeUnit | None:
        if self._closed:
            raise RuntimeError("SqliteStore is closed")
        with self._engine.connect() as conn:
            row = conn.execute(SELECT_BY_ID, {"id": unit_id}).fetchone()
        return KnowledgeUnit.model_validate_json(row[0]) if row is not None else None

    async def get_review_status(self, unit_id: str) -> dict[str, str | None] | None:
        return await self._run_sync(self._get_review_status_sync, unit_id)

    def _get_review_status_sync(self, unit_id: str) -> dict[str, str | None] | None:
        if self._closed:
            raise RuntimeError("SqliteStore is closed")
        with self._engine.connect() as conn:
            row = conn.execute(SELECT_REVIEW_STATUS_BY_ID, {"id": unit_id}).fetchone()
        if row is None:
            return None
        return {"status": row[0], "reviewed_by": row[1], "reviewed_at": row[2]}

    async def set_review_status(self, unit_id: str, status: str, reviewed_by: str) -> None:
        await self._run_sync(self._set_review_status_sync, unit_id, status, reviewed_by)

    def _set_review_status_sync(self, unit_id: str, status: str, reviewed_by: str) -> None:
        if self._closed:
            raise RuntimeError("SqliteStore is closed")
        reviewed_at = datetime.now(UTC).isoformat()
        with self._engine.begin() as conn:
            cursor = conn.execute(
                UPDATE_REVIEW_STATUS,
                {"id": unit_id, "status": status, "reviewed_by": reviewed_by, "reviewed_at": reviewed_at},
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Knowledge unit not found: {unit_id}")

    async def update(self, unit: KnowledgeUnit) -> None:
        await self._run_sync(self._update_sync, unit)

    def _update_sync(self, unit: KnowledgeUnit) -> None:
        if self._closed:
            raise RuntimeError("SqliteStore is closed")
        domains = normalize_domains(unit.domains)
        if not domains:
            raise ValueError("knowledge unit must have at least one domain")
        with self._engine.begin() as conn:
            cursor = conn.execute(
                UPDATE_UNIT_DATA,
                {"id": unit.id, "data": unit.model_dump_json(), "tier": unit.tier.value},
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Knowledge unit not found: {unit.id}")
            conn.execute(DELETE_UNIT_DOMAINS, {"unit_id": unit.id})
            for d in domains:
                conn.execute(INSERT_UNIT_DOMAIN, {"unit_id": unit.id, "domain": d})

    async def query(
        self,
        domains: list[str],
        *,
        languages: list[str] | None = None,
        frameworks: list[str] | None = None,
        pattern: str = "",
        limit: int = 5,
    ) -> list[KnowledgeUnit]:
        return await self._run_sync(
            self._query_sync,
            domains,
            languages=languages,
            frameworks=frameworks,
            pattern=pattern,
            limit=limit,
        )

    def _query_sync(
        self,
        domains: list[str],
        *,
        languages: list[str] | None,
        frameworks: list[str] | None,
        pattern: str,
        limit: int,
    ) -> list[KnowledgeUnit]:
        if self._closed:
            raise RuntimeError("SqliteStore is closed")
        normalized = normalize_domains(domains)
        if not normalized:
            return []
        with self._engine.connect() as conn:
            rows = conn.execute(SELECT_QUERY_UNITS, {"domains": normalized}).fetchall()
        units = [KnowledgeUnit.model_validate_json(row[0]) for row in rows]
        scored = [
            (
                calculate_relevance(
                    u,
                    normalized,
                    query_languages=languages,
                    query_frameworks=frameworks,
                    query_pattern=pattern,
                )
                * u.evidence.confidence,
                u.id,
                u,
            )
            for u in units
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [u for _, _, u in scored[:limit]]

    async def count(self) -> int:
        return await self._run_sync(self._count_sync)

    def _count_sync(self) -> int:
        with self._engine.connect() as conn:
            return int(conn.execute(SELECT_TOTAL_COUNT).scalar() or 0)

    async def domain_counts(self) -> dict[str, int]:
        return await self._run_sync(self._domain_counts_sync)

    def _domain_counts_sync(self) -> dict[str, int]:
        with self._engine.connect() as conn:
            rows = conn.execute(SELECT_DOMAIN_COUNTS).fetchall()
        return {row[0]: row[1] for row in rows}

    async def pending_queue(self, *, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def pending_count(self) -> int:
        raise NotImplementedError

    async def counts_by_status(self) -> dict[str, int]:
        return await self._run_sync(self._counts_by_status_sync)

    def _counts_by_status_sync(self) -> dict[str, int]:
        with self._engine.connect() as conn:
            rows = conn.execute(SELECT_COUNTS_BY_STATUS).fetchall()
        return {row[0]: row[1] for row in rows}

    async def counts_by_tier(self) -> dict[str, int]:
        return await self._run_sync(self._counts_by_tier_sync)

    def _counts_by_tier_sync(self) -> dict[str, int]:
        with self._engine.connect() as conn:
            rows = conn.execute(SELECT_COUNTS_BY_TIER).fetchall()
        return {row[0]: row[1] for row in rows}

    async def list_units(
        self,
        *,
        domain: str | None = None,
        confidence_min: float | None = None,
        confidence_max: float | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def create_user(self, username: str, password_hash: str) -> None:
        raise NotImplementedError

    async def get_user(self, username: str) -> dict[str, Any] | None:
        raise NotImplementedError

    async def count_active_api_keys_for_user(self, user_id: int) -> int:
        raise NotImplementedError

    async def create_api_key(
        self,
        *,
        key_id: str,
        user_id: int,
        name: str,
        labels: list[str],
        key_prefix: str,
        key_hash: str,
        ttl: str,
        expires_at: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def get_api_key_for_user(self, *, user_id: int, key_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    async def get_active_api_key_by_id(self, key_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    async def list_api_keys_for_user(self, user_id: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def revoke_api_key(self, *, user_id: int, key_id: str) -> bool:
        raise NotImplementedError

    async def touch_api_key_last_used(self, key_id: str) -> None:
        raise NotImplementedError

    async def confidence_distribution(self) -> dict[str, int]:
        raise NotImplementedError

    async def recent_activity(self, limit: int = 20) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def daily_counts(self, *, days: int = 30) -> list[dict[str, Any]]:
        raise NotImplementedError
