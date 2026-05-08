"""Knowledge-unit repository: insert, fetch, update, query, and aggregations."""

from __future__ import annotations

from datetime import UTC, datetime

from cq.models import KnowledgeUnit
from sqlalchemy.exc import IntegrityError

from ..core.db import Database
from ..scoring import calculate_relevance
from ._normalize import normalize_domains
from ._queries import (
    DELETE_UNIT_DOMAINS,
    INSERT_UNIT,
    INSERT_UNIT_DOMAIN,
    SELECT_APPROVED_BY_ID,
    SELECT_BY_ID,
    SELECT_COUNTS_BY_TIER,
    SELECT_DOMAIN_COUNTS,
    SELECT_QUERY_UNITS,
    SELECT_TOTAL_COUNT,
    UPDATE_UNIT_DATA,
)


class KnowledgeRepository:
    """Read/write access to knowledge units."""

    def __init__(self, db: Database) -> None:
        """Wire the repository to the shared ``Database``."""
        self._db = db

    async def count(self) -> int:
        """Return the total number of stored units across all review statuses."""
        return await self._db.run_sync(self._count_sync)

    async def counts_by_tier(self) -> dict[str, int]:
        """Return approved-unit counts grouped by tier."""
        return await self._db.run_sync(self._counts_by_tier_sync)

    async def domain_counts(self) -> dict[str, int]:
        """Return unit counts per normalised domain tag."""
        return await self._db.run_sync(self._domain_counts_sync)

    async def get(self, unit_id: str) -> KnowledgeUnit | None:
        """Return an approved unit by id, or ``None`` if missing or pending."""
        return await self._db.run_sync(self._get_sync, unit_id)

    async def get_any(self, unit_id: str) -> KnowledgeUnit | None:
        """Return a unit by id regardless of review status, or ``None``."""
        return await self._db.run_sync(self._get_any_sync, unit_id)

    async def insert(self, unit: KnowledgeUnit) -> None:
        """Persist a new unit. Domains are normalised; raises on integrity failure."""
        await self._db.run_sync(self._insert_sync, unit)

    async def query(
        self,
        domains: list[str],
        *,
        languages: list[str] | None = None,
        frameworks: list[str] | None = None,
        pattern: str = "",
        limit: int = 5,
    ) -> list[KnowledgeUnit]:
        """Return approved units matching ``domains``, ranked by relevance × confidence."""
        return await self._db.run_sync(
            self._query_sync,
            domains,
            languages=languages,
            frameworks=frameworks,
            pattern=pattern,
            limit=limit,
        )

    async def update(self, unit: KnowledgeUnit) -> None:
        """Persist changes to an existing unit; raises ``KeyError`` if unknown."""
        await self._db.run_sync(self._update_sync, unit)

    def _count_sync(self) -> int:
        with self._db.engine.connect() as conn:
            return int(conn.execute(SELECT_TOTAL_COUNT).scalar() or 0)

    def _counts_by_tier_sync(self) -> dict[str, int]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(SELECT_COUNTS_BY_TIER).fetchall()
        return {row[0]: row[1] for row in rows}

    def _domain_counts_sync(self) -> dict[str, int]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(SELECT_DOMAIN_COUNTS).fetchall()
        return {row[0]: row[1] for row in rows}

    def _get_any_sync(self, unit_id: str) -> KnowledgeUnit | None:
        with self._db.engine.connect() as conn:
            row = conn.execute(SELECT_BY_ID, {"id": unit_id}).fetchone()
        return KnowledgeUnit.model_validate_json(row[0]) if row is not None else None

    def _get_sync(self, unit_id: str) -> KnowledgeUnit | None:
        with self._db.engine.connect() as conn:
            row = conn.execute(SELECT_APPROVED_BY_ID, {"id": unit_id}).fetchone()
        return KnowledgeUnit.model_validate_json(row[0]) if row is not None else None

    def _insert_sync(self, unit: KnowledgeUnit) -> None:
        domains = normalize_domains(unit.domains)
        if not domains:
            raise ValueError("At least one non-empty domain is required")
        # Persist the normalised form in both the JSON blob and the
        # knowledge_unit_domains rows so calculate_relevance reads the
        # same domains from either source.
        unit = unit.model_copy(update={"domains": domains})
        created_at = (
            unit.evidence.first_observed.isoformat() if unit.evidence.first_observed else datetime.now(UTC).isoformat()
        )
        try:
            with self._db.engine.begin() as conn:
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
        with self._db.engine.connect() as conn:
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

    def _update_sync(self, unit: KnowledgeUnit) -> None:
        domains = normalize_domains(unit.domains)
        if not domains:
            raise ValueError("At least one non-empty domain is required")
        unit = unit.model_copy(update={"domains": domains})
        try:
            with self._db.engine.begin() as conn:
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
