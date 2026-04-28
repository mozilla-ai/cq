"""SqliteStore: SQLite-backed implementation of the async Store protocol.

Async surface implemented as a threadpool shim over a sync SQLAlchemy Core
engine. SQLite-native concerns (PRAGMAs, single-writer behaviour) live here;
portable SQL is sourced from ``cq_server.store._queries``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cq.models import KnowledgeUnit
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..scoring import calculate_relevance
from ..tables import ensure_api_keys_table, ensure_review_columns, ensure_users_table
from ._normalize import normalize_domains
from ._queries import (
    COUNT_ACTIVE_KEYS_FOR_USER,
    DELETE_UNIT_DOMAINS,
    INSERT_API_KEY,
    INSERT_UNIT,
    INSERT_UNIT_DOMAIN,
    SELECT_APPROVED_BY_ID,
    SELECT_APPROVED_DATA,
    SELECT_BY_ID,
    SELECT_COUNTS_BY_STATUS,
    SELECT_COUNTS_BY_TIER,
    SELECT_DOMAIN_COUNTS,
    SELECT_KEY_FOR_USER,
    SELECT_PENDING_COUNT,
    SELECT_PENDING_QUEUE,
    SELECT_QUERY_UNITS,
    SELECT_RECENT_ACTIVITY,
    SELECT_REVIEW_STATUS_BY_ID,
    SELECT_TOTAL_COUNT,
    UPDATE_REVIEW_STATUS,
    UPDATE_UNIT_DATA,
)

_logger = logging.getLogger(__name__)

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

    async def confidence_distribution(self) -> dict[str, int]:
        return await self._run_sync(self._confidence_distribution_sync)

    async def count(self) -> int:
        return await self._run_sync(self._count_sync)

    async def count_active_api_keys_for_user(self, user_id: int) -> int:
        return await self._run_sync(self._count_active_api_keys_for_user_sync, user_id)

    async def counts_by_status(self) -> dict[str, int]:
        return await self._run_sync(self._counts_by_status_sync)

    async def counts_by_tier(self) -> dict[str, int]:
        return await self._run_sync(self._counts_by_tier_sync)

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
        return await self._run_sync(
            self._create_api_key_sync,
            key_id=key_id,
            user_id=user_id,
            name=name,
            labels=labels,
            key_prefix=key_prefix,
            key_hash=key_hash,
            ttl=ttl,
            expires_at=expires_at,
        )

    async def create_user(self, username: str, password_hash: str) -> None:
        await self._run_sync(self._create_user_sync, username, password_hash)

    async def daily_counts(self, *, days: int = 30) -> list[dict[str, Any]]:
        if days <= 0:
            raise ValueError("days must be positive")
        return await self._run_sync(self._daily_counts_sync, days=days)

    async def domain_counts(self) -> dict[str, int]:
        return await self._run_sync(self._domain_counts_sync)

    async def get(self, unit_id: str) -> KnowledgeUnit | None:
        return await self._run_sync(self._get_sync, unit_id)

    async def get_active_api_key_by_id(self, key_id: str) -> dict[str, Any] | None:
        return await self._run_sync(self._get_active_api_key_by_id_sync, key_id)

    async def get_any(self, unit_id: str) -> KnowledgeUnit | None:
        return await self._run_sync(self._get_any_sync, unit_id)

    async def get_api_key_for_user(self, *, user_id: int, key_id: str) -> dict[str, Any] | None:
        return await self._run_sync(self._get_api_key_for_user_sync, user_id=user_id, key_id=key_id)

    async def get_review_status(self, unit_id: str) -> dict[str, str | None] | None:
        return await self._run_sync(self._get_review_status_sync, unit_id)

    async def get_user(self, username: str) -> dict[str, Any] | None:
        return await self._run_sync(self._get_user_sync, username)

    async def insert(self, unit: KnowledgeUnit) -> None:
        await self._run_sync(self._insert_sync, unit)

    async def list_api_keys_for_user(self, user_id: int) -> list[dict[str, Any]]:
        return await self._run_sync(self._list_api_keys_for_user_sync, user_id)

    async def list_units(
        self,
        *,
        domain: str | None = None,
        confidence_min: float | None = None,
        confidence_max: float | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return await self._run_sync(
            self._list_units_sync,
            domain=domain,
            confidence_min=confidence_min,
            confidence_max=confidence_max,
            status=status,
            limit=limit,
        )

    async def pending_count(self) -> int:
        return await self._run_sync(self._pending_count_sync)

    async def pending_queue(self, *, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        return await self._run_sync(self._pending_queue_sync, limit=limit, offset=offset)

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

    async def recent_activity(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self._run_sync(self._recent_activity_sync, limit=limit)

    async def revoke_api_key(self, *, user_id: int, key_id: str) -> bool:
        return await self._run_sync(self._revoke_api_key_sync, user_id=user_id, key_id=key_id)

    async def set_review_status(self, unit_id: str, status: str, reviewed_by: str) -> None:
        await self._run_sync(self._set_review_status_sync, unit_id, status, reviewed_by)

    async def touch_api_key_last_used(self, key_id: str) -> None:
        await self._run_sync(self._touch_api_key_last_used_sync, key_id)

    async def update(self, unit: KnowledgeUnit) -> None:
        await self._run_sync(self._update_sync, unit)

    def _confidence_distribution_sync(self) -> dict[str, int]:
        buckets = {"0.0-0.3": 0, "0.3-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
        with self._engine.connect() as conn:
            rows = conn.execute(SELECT_APPROVED_DATA).fetchall()
        for row in rows:
            c = KnowledgeUnit.model_validate_json(row[0]).evidence.confidence
            if c < 0.3:
                buckets["0.0-0.3"] += 1
            elif c < 0.6:
                buckets["0.3-0.6"] += 1
            elif c < 0.8:
                buckets["0.6-0.8"] += 1
            else:
                buckets["0.8-1.0"] += 1
        return buckets

    def _count_active_api_keys_for_user_sync(self, user_id: int) -> int:
        now = datetime.now(UTC).isoformat()
        with self._engine.connect() as conn:
            row = conn.execute(COUNT_ACTIVE_KEYS_FOR_USER, {"user_id": user_id, "now": now}).fetchone()
        return int(row[0]) if row is not None else 0

    def _count_sync(self) -> int:
        with self._engine.connect() as conn:
            return int(conn.execute(SELECT_TOTAL_COUNT).scalar() or 0)

    def _counts_by_status_sync(self) -> dict[str, int]:
        with self._engine.connect() as conn:
            rows = conn.execute(SELECT_COUNTS_BY_STATUS).fetchall()
        return {row[0]: row[1] for row in rows}

    def _counts_by_tier_sync(self) -> dict[str, int]:
        with self._engine.connect() as conn:
            rows = conn.execute(SELECT_COUNTS_BY_TIER).fetchall()
        return {row[0]: row[1] for row in rows}

    def _create_api_key_sync(
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
        created_at = datetime.now(UTC).isoformat()
        labels_json = json.dumps(labels)
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    INSERT_API_KEY,
                    {
                        "id": key_id,
                        "user_id": user_id,
                        "name": name,
                        "labels": labels_json,
                        "key_prefix": key_prefix,
                        "key_hash": key_hash,
                        "ttl": ttl,
                        "expires_at": expires_at,
                        "created_at": created_at,
                    },
                )
        except IntegrityError as e:
            if e.orig is not None:
                raise e.orig from e
            raise
        return {
            "id": key_id,
            "user_id": user_id,
            "name": name,
            "labels": list(labels),
            "key_prefix": key_prefix,
            "key_hash": key_hash,
            "ttl": ttl,
            "expires_at": expires_at,
            "created_at": created_at,
            "last_used_at": None,
            "revoked_at": None,
        }

    def _create_user_sync(self, username: str, password_hash: str) -> None:
        from ._queries import INSERT_USER

        created_at = datetime.now(UTC).isoformat()
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    INSERT_USER,
                    {"username": username, "password_hash": password_hash, "created_at": created_at},
                )
        except IntegrityError as e:
            if e.orig is not None:
                raise e.orig from e
            raise

    def _daily_counts_sync(self, *, days: int) -> list[dict[str, Any]]:
        cutoff = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
        from ._queries import SELECT_APPROVED_DAILY, SELECT_PROPOSED_DAILY, SELECT_REJECTED_DAILY

        with self._engine.connect() as conn:
            proposed = {row[0]: row[1] for row in conn.execute(SELECT_PROPOSED_DAILY, {"cutoff": cutoff}).fetchall()}
            approved = {row[0]: row[1] for row in conn.execute(SELECT_APPROVED_DAILY, {"cutoff": cutoff}).fetchall()}
            rejected = {row[0]: row[1] for row in conn.execute(SELECT_REJECTED_DAILY, {"cutoff": cutoff}).fetchall()}
        all_dates = set(proposed) | set(approved) | set(rejected)
        if not all_dates:
            return []
        start = min(datetime.strptime(d, "%Y-%m-%d").date() for d in all_dates)
        end = datetime.now(UTC).date()
        rows: list[dict[str, Any]] = []
        current = start
        while current <= end:
            key = current.isoformat()
            rows.append(
                {
                    "date": key,
                    "proposed": proposed.get(key, 0),
                    "approved": approved.get(key, 0),
                    "rejected": rejected.get(key, 0),
                }
            )
            current += timedelta(days=1)
        return rows

    def _domain_counts_sync(self) -> dict[str, int]:
        with self._engine.connect() as conn:
            rows = conn.execute(SELECT_DOMAIN_COUNTS).fetchall()
        return {row[0]: row[1] for row in rows}

    def _get_active_api_key_by_id_sync(self, key_id: str) -> dict[str, Any] | None:
        now = datetime.now(UTC).isoformat()
        # JOIN on users to surface the owner's username. Inline because no
        # _queries.py constant covers this shape; promotion left to a
        # follow-up — out of scope per #308.
        stmt = text(
            "SELECT k.id, k.user_id, u.username, k.name, k.labels, k.key_prefix, "
            "k.key_hash, k.ttl, k.expires_at, k.created_at, k.last_used_at, k.revoked_at "
            "FROM api_keys k JOIN users u ON u.id = k.user_id "
            "WHERE k.id = :key_id AND k.revoked_at IS NULL AND k.expires_at > :now"
        )
        with self._engine.connect() as conn:
            row = conn.execute(stmt, {"key_id": key_id, "now": now}).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "user_id": row[1],
            "username": row[2],
            "name": row[3],
            "labels": json.loads(row[4] or "[]"),
            "key_prefix": row[5],
            "key_hash": row[6],
            "ttl": row[7],
            "expires_at": row[8],
            "created_at": row[9],
            "last_used_at": row[10],
            "revoked_at": row[11],
        }

    def _get_any_sync(self, unit_id: str) -> KnowledgeUnit | None:
        with self._engine.connect() as conn:
            row = conn.execute(SELECT_BY_ID, {"id": unit_id}).fetchone()
        return KnowledgeUnit.model_validate_json(row[0]) if row is not None else None

    def _get_api_key_for_user_sync(self, *, user_id: int, key_id: str) -> dict[str, Any] | None:
        with self._engine.connect() as conn:
            row = conn.execute(SELECT_KEY_FOR_USER, {"key_id": key_id, "user_id": user_id}).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "user_id": row[1],
            "name": row[2],
            "labels": json.loads(row[3] or "[]"),
            "key_prefix": row[4],
            "ttl": row[5],
            "expires_at": row[6],
            "created_at": row[7],
            "last_used_at": row[8],
            "revoked_at": row[9],
        }

    def _get_review_status_sync(self, unit_id: str) -> dict[str, str | None] | None:
        with self._engine.connect() as conn:
            row = conn.execute(SELECT_REVIEW_STATUS_BY_ID, {"id": unit_id}).fetchone()
        if row is None:
            return None
        return {"status": row[0], "reviewed_by": row[1], "reviewed_at": row[2]}

    def _get_sync(self, unit_id: str) -> KnowledgeUnit | None:
        with self._engine.connect() as conn:
            row = conn.execute(SELECT_APPROVED_BY_ID, {"id": unit_id}).fetchone()
        return KnowledgeUnit.model_validate_json(row[0]) if row is not None else None

    def _get_user_sync(self, username: str) -> dict[str, Any] | None:
        from ._queries import SELECT_USER_BY_USERNAME

        with self._engine.connect() as conn:
            row = conn.execute(SELECT_USER_BY_USERNAME, {"username": username}).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "created_at": row[3],
        }

    def _insert_sync(self, unit: KnowledgeUnit) -> None:
        domains = normalize_domains(unit.domains)
        if not domains:
            raise ValueError("At least one non-empty domain is required")
        # Persist the normalized form in both the JSON blob and the
        # knowledge_unit_domains rows so calculate_relevance reads the
        # same domains from either source.
        unit = unit.model_copy(update={"domains": domains})
        created_at = (
            unit.evidence.first_observed.isoformat() if unit.evidence.first_observed else datetime.now(UTC).isoformat()
        )
        try:
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
        except IntegrityError as e:
            if e.orig is not None:
                raise e.orig from e
            raise

    def _list_api_keys_for_user_sync(self, user_id: int) -> list[dict[str, Any]]:
        # Inline SQL: no _queries.py constant covers this list shape.
        stmt = text(
            "SELECT id, name, labels, key_prefix, ttl, expires_at, created_at, "
            "last_used_at, revoked_at "
            "FROM api_keys WHERE user_id = :user_id ORDER BY created_at DESC"
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt, {"user_id": user_id}).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "labels": json.loads(row[2] or "[]"),
                "key_prefix": row[3],
                "ttl": row[4],
                "expires_at": row[5],
                "created_at": row[6],
                "last_used_at": row[7],
                "revoked_at": row[8],
            }
            for row in rows
        ]

    def _list_units_sync(
        self,
        *,
        domain: str | None,
        confidence_min: float | None,
        confidence_max: float | None,
        status: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        from ._queries import select_list_units

        normalized_domain: str | None = None
        if domain is not None and domain.strip():
            normalized_domain = domain.strip().lower()

        normalized_status: str | None = status if (status is not None and status.strip()) else None

        confidence_filter_active = confidence_min is not None or confidence_max is not None
        stmt = select_list_units(
            domain=normalized_domain,
            status=normalized_status,
            apply_limit=not confidence_filter_active,
        )
        params: dict[str, Any] = {}
        if normalized_domain is not None:
            params["domain"] = normalized_domain
        if normalized_status is not None:
            params["status"] = normalized_status
        if not confidence_filter_active:
            params["limit"] = limit

        with self._engine.connect() as conn:
            rows = conn.execute(stmt, params).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            unit = KnowledgeUnit.model_validate_json(row[0])
            c = unit.evidence.confidence
            if confidence_min is not None and c < confidence_min:
                continue
            if confidence_max is not None and (c > confidence_max or (c >= confidence_max and confidence_max < 1.0)):
                continue
            results.append(
                {
                    "knowledge_unit": unit,
                    "status": row[1] or "pending",
                    "reviewed_by": row[2],
                    "reviewed_at": row[3],
                }
            )
            if len(results) >= limit:
                break
        return results

    def _pending_count_sync(self) -> int:
        with self._engine.connect() as conn:
            return int(conn.execute(SELECT_PENDING_COUNT).scalar() or 0)

    def _pending_queue_sync(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        with self._engine.connect() as conn:
            rows = conn.execute(SELECT_PENDING_QUEUE, {"limit": limit, "offset": offset}).fetchall()
        return [
            {
                "knowledge_unit": KnowledgeUnit.model_validate_json(row[0]),
                "status": row[1] or "pending",
                "reviewed_by": row[2],
                "reviewed_at": row[3],
            }
            for row in rows
        ]

    def _query_sync(
        self,
        domains: list[str],
        *,
        languages: list[str] | None,
        frameworks: list[str] | None,
        pattern: str,
        limit: int,
    ) -> list[KnowledgeUnit]:
        if limit <= 0:
            raise ValueError("limit must be positive")
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
        # Match RemoteStore tie-break: score desc, id desc on tie.
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [u for _, _, u in scored[:limit]]

    def _recent_activity_sync(self, *, limit: int) -> list[dict[str, Any]]:
        # Over-fetch by 2x to give buffer; the SELECT already ORDER BYs
        # COALESCE(reviewed_at, created_at) DESC. Final slice trims to limit.
        with self._engine.connect() as conn:
            rows = conn.execute(SELECT_RECENT_ACTIVITY, {"limit": limit * 2}).fetchall()
        activity: list[dict[str, Any]] = []
        for row in rows:
            unit = KnowledgeUnit.model_validate_json(row[1])
            proposed_ts = unit.evidence.first_observed.isoformat() if unit.evidence.first_observed else ""
            if row[2] in ("approved", "rejected"):
                activity.append(
                    {
                        "type": row[2],
                        "unit_id": row[0],
                        "summary": unit.insight.summary,
                        "reviewed_by": row[3],
                        "timestamp": row[4] or proposed_ts,
                    }
                )
            else:
                activity.append(
                    {
                        "type": "proposed",
                        "unit_id": row[0],
                        "summary": unit.insight.summary,
                        "timestamp": proposed_ts,
                    }
                )
        return activity[:limit]

    def _revoke_api_key_sync(self, *, user_id: int, key_id: str) -> bool:
        now = datetime.now(UTC).isoformat()
        # Inline SQL: no _queries.py constant covers this update shape.
        # The "revoked_at IS NULL" guard is what makes the second revoke a no-op.
        stmt = text(
            "UPDATE api_keys SET revoked_at = :now WHERE id = :key_id AND user_id = :user_id AND revoked_at IS NULL"
        )
        with self._engine.begin() as conn:
            cursor = conn.execute(stmt, {"now": now, "key_id": key_id, "user_id": user_id})
        return cursor.rowcount > 0

    async def _run_sync(self, fn, /, *args, **kwargs):
        """Run a sync callable on the default executor and await its result.

        All public async methods funnel SQL work through this shim so the
        sqlite3 driver's blocking calls don't tie up the event-loop thread.
        Centralises the closed-store guard so every public method rejects
        calls after ``close()``.
        """
        if self._closed:
            raise RuntimeError("SqliteStore is closed")
        return await asyncio.to_thread(fn, *args, **kwargs)

    def _set_review_status_sync(self, unit_id: str, status: str, reviewed_by: str) -> None:
        reviewed_at = datetime.now(UTC).isoformat()
        with self._engine.begin() as conn:
            cursor = conn.execute(
                UPDATE_REVIEW_STATUS,
                {"id": unit_id, "status": status, "reviewed_by": reviewed_by, "reviewed_at": reviewed_at},
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Knowledge unit not found: {unit_id}")

    def _touch_api_key_last_used_sync(self, key_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        stmt = text("UPDATE api_keys SET last_used_at = :now WHERE id = :key_id")
        try:
            with self._engine.begin() as conn:
                conn.execute(stmt, {"now": now, "key_id": key_id})
        except SQLAlchemyError:
            # Observability hook only; failures must not break the request path.
            _logger.exception("Failed to update last_used_at for api key %s", key_id)

    def _update_sync(self, unit: KnowledgeUnit) -> None:
        domains = normalize_domains(unit.domains)
        if not domains:
            raise ValueError("At least one non-empty domain is required")
        unit = unit.model_copy(update={"domains": domains})
        try:
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
        except IntegrityError as e:
            if e.orig is not None:
                raise e.orig from e
            raise
