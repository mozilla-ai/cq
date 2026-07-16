"""Knowledge-unit repository: insert, fetch, update, query, and aggregations."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from cq.models import KnowledgeUnit
from cq.scoring import calculate_relevance
from sqlalchemy.exc import IntegrityError

from ..core.db import Database
from ..semsearch import _ENABLED as _SEMSEARCH_ENABLED
from ..semsearch.queries import EmbeddingServiceError
from ..semsearch.queries import combined_query as sem_query
from ..semsearch.queries import insert_unit as sem_insert_unit
from ..semsearch.queries import update_unit as sem_update_unit
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
    confidence_distribution_sql,
    resolve_dialect,
)

logger = logging.getLogger(__name__)

# Mirrors `cq.store._CONFIDENCE_BUCKETS`. Each entry is `(exclusive upper
# bound, label)`, ordered low to high; the last entry's `inf` upper bound is
# the catch-all. Single source for the result dict's key set and ordering.
_CONFIDENCE_BUCKETS: list[tuple[float, str]] = [
    (0.3, "0.0-0.3"),
    (0.5, "0.3-0.5"),
    (0.7, "0.5-0.7"),
    (float("inf"), "0.7-1.0"),
]

# Bucket approved units by their persisted confidence in SQL (built from the
# single `_CONFIDENCE_BUCKETS` source above) rather than parsing every unit
# into a model to read one float. See `confidence_distribution_sql` for the
# dialect handling; resolved once per repo from the engine dialect in `__init__`.


class KnowledgeRepository:
    """Read/write access to knowledge units."""

    def __init__(self, db: Database) -> None:
        """Wire the repository to the shared ``Database``."""
        self._db = db
        dialect = resolve_dialect(db.engine.dialect.name)
        self._confidence_distribution_stmt = confidence_distribution_sql(_CONFIDENCE_BUCKETS, dialect)

    async def count(self) -> int:
        """Return the total number of stored units across all review statuses."""
        return await self._db.run_sync(self._count_sync)

    async def confidence_distribution(self) -> dict[str, int]:
        """Return approved-unit counts grouped into the canonical confidence buckets."""
        return await self._db.run_sync(self._confidence_distribution_sync)

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
        """Persist a new KnowledgeUnit to the repository.

        Normalizes the unit's domains and inserts the unit and its domain mappings into the database.
            If semantic-search integration is enabled, the unit is also inserted into the semsearch
            store in a separate transaction.

        Parameters:
            unit (KnowledgeUnit): The knowledge unit to persist; its domains will be normalized before storage.

        Raises:
            ValueError: If normalization yields no domains.
            sqlalchemy.IntegrityError: On database integrity constraint violations
                (the original DB error may be re-raised).
        """
        if _SEMSEARCH_ENABLED:
            await sem_insert_unit(self._db, unit, self.build_insert_clauses(unit))
        else:
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
        """Find approved KUs matching domains, ordered by relevance times confidence.

        This method finds approved knowledge units matching the given domains, ordered by
            relevance multiplied by the unit's evidence confidence.

        Parameters:
            domains (list[str]): Domains to match against (domain strings).
            languages (list[str] | None): Optional language filters that influence relevance scoring.
            frameworks (list[str] | None): Optional framework filters that influence relevance scoring.
            pattern (str): Optional textual pattern to match; affects relevance.
            limit (int): Maximum number of units to return; must be greater than zero.

        Returns:
            list[KnowledgeUnit]: A list of matching approved knowledge units ordered by relevance × confidence.
        """
        if _SEMSEARCH_ENABLED:
            try:
                normalized, clauses = self.build_query_clauses(domains)
                if not normalized:
                    return []
                return await sem_query(
                    self._db,
                    domains,
                    languages=languages,
                    frameworks=frameworks,
                    pattern=pattern,
                    limit=limit,
                    base_clauses=clauses,
                )
            except EmbeddingServiceError as e:
                logger.warning(f"Semantic search query failed: {e}")
                logger.warning("Fallback to SQL query")
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
        if _SEMSEARCH_ENABLED:
            exists_rows = await self._db.run_sync(
                self._db.run_clauses_sync,
                self.build_exists_by_id_clauses(unit.id),
                fetch=True,
            )
            if not exists_rows:
                raise KeyError(f"Knowledge unit not found: {unit.id}")
            await sem_update_unit(self._db, unit, self.build_update_clauses(unit))
            return
        await self._db.run_sync(self._update_sync, unit)

    def _count_sync(self) -> int:
        with self._db.engine.connect() as conn:
            return int(conn.execute(SELECT_TOTAL_COUNT).scalar() or 0)

    def _confidence_distribution_sync(self) -> dict[str, int]:
        # Seed every canonical bucket so absent labels report 0; the SQL only
        # returns rows for buckets that have at least one approved unit.
        buckets = {label: 0 for _, label in _CONFIDENCE_BUCKETS}
        with self._db.engine.connect() as conn:
            rows = conn.execute(self._confidence_distribution_stmt).fetchall()
        for label, count in rows:
            buckets[label] = count
        return buckets

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
        self._db.run_clauses_sync(self.build_insert_clauses(unit))

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
        normalized, clauses = self.build_query_clauses(domains)
        if not normalized:
            return []
        rows = self._db.run_clauses_sync(clauses, fetch=True)
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
        try:
            exists_rows = self._db.run_clauses_sync(self.build_exists_by_id_clauses(unit.id), fetch=True)
            if not exists_rows:
                raise KeyError(f"Knowledge unit not found: {unit.id}")
            self._db.run_clauses_sync(self.build_update_clauses(unit))
        except IntegrityError as e:
            if e.orig is not None:
                raise e.orig from e
            raise

    def build_query_clauses(self, domains: list[str]) -> tuple[list[str], list[tuple[Any, dict[str, Any]]]]:
        """Build SELECT clauses for querying approved units by normalized domains."""
        normalized = normalize_domains(domains)
        return normalized, [(SELECT_QUERY_UNITS, {"domains": normalized})]

    def build_exists_by_id_clauses(self, unit_id: str) -> list[tuple[Any, dict[str, Any]]]:
        """Build clauses to check whether a knowledge unit id exists."""
        return [(SELECT_BY_ID, {"id": unit_id})]

    def build_insert_clauses(self, unit: KnowledgeUnit) -> list[tuple[Any, dict[str, Any]]]:
        """Build insert clauses for a unit and all of its normalized domains."""
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

        clauses: list[tuple[Any, dict[str, Any]]] = [
            (
                INSERT_UNIT,
                {
                    "id": unit.id,
                    "data": unit.model_dump_json(exclude_none=True),
                    "created_at": created_at,
                    "tier": unit.tier.value,
                },
            ),
        ]
        for domain in domains:
            clauses.append((INSERT_UNIT_DOMAIN, {"unit_id": unit.id, "domain": domain}))
        return clauses

    def build_update_clauses(self, unit: KnowledgeUnit) -> list[tuple[Any, dict[str, Any]]]:
        """Build update clauses for unit JSON/tier and normalized domain mappings."""
        domains = normalize_domains(unit.domains)
        if not domains:
            raise ValueError("At least one non-empty domain is required")
        unit = unit.model_copy(update={"domains": domains})

        clauses: list[tuple[Any, dict[str, Any]]] = [
            (
                UPDATE_UNIT_DATA,
                {"id": unit.id, "data": unit.model_dump_json(exclude_none=True), "tier": unit.tier.value},
            ),
            (DELETE_UNIT_DOMAINS, {"unit_id": unit.id}),
        ]
        for domain in domains:
            clauses.append((INSERT_UNIT_DOMAIN, {"unit_id": unit.id, "domain": domain}))
        return clauses
