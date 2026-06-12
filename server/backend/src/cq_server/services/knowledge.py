"""Knowledge service: propose, query, confirm, flag, and stats."""

from __future__ import annotations

from cq.models import Context, FlagReason, Insight, KnowledgeUnit, Tier, create_knowledge_unit
from cq.scoring import apply_confirmation, apply_flag

from ..exceptions import InvalidDomainError, KnowledgeUnitNotFoundError
from ..models.knowledge import StatsResponse
from ..repositories import KnowledgeRepository, normalize_domains


class KnowledgeService:
    """Apply normalisation + scoring rules around the knowledge repository."""

    def __init__(self, *, knowledge: KnowledgeRepository) -> None:
        """Compose the service over the knowledge repository."""
        self._knowledge = knowledge

    async def confirm(self, unit_id: str) -> KnowledgeUnit:
        """Apply a confirmation to ``unit_id``, persist, and return it.

        Raises:
            KnowledgeUnitNotFoundError: If the unit is unknown or not approved.
        """
        unit = await self._knowledge.get(unit_id)
        if unit is None:
            raise KnowledgeUnitNotFoundError()
        confirmed = apply_confirmation(unit)
        await self._knowledge.update(confirmed)
        return confirmed

    async def flag(self, unit_id: str, reason: FlagReason) -> KnowledgeUnit:
        """Apply a flag to ``unit_id``, persist, and return the updated unit.

        Raises:
            KnowledgeUnitNotFoundError: If the unit is unknown or not approved.
        """
        unit = await self._knowledge.get(unit_id)
        if unit is None:
            raise KnowledgeUnitNotFoundError()
        flagged = apply_flag(unit, reason)
        await self._knowledge.update(flagged)
        return flagged

    async def propose(
        self,
        *,
        domains: list[str],
        insight: Insight,
        context: Context,
        created_by: str,
    ) -> KnowledgeUnit:
        """Create + persist a new knowledge unit owned by ``created_by``.

        The caller has already been authenticated; ``created_by`` is the
        authoritative username from the credential, never client input.

        Raises:
            InvalidDomainError: If all supplied domains are empty/whitespace.
        """
        normalized = normalize_domains(domains)
        if not normalized:
            raise InvalidDomainError()
        unit = create_knowledge_unit(
            domains=normalized,
            insight=insight,
            context=context,
            tier=Tier.PRIVATE,
            created_by=created_by,
        )
        await self._knowledge.insert(unit)
        return unit

    async def query(
        self,
        *,
        domains: list[str],
        languages: list[str] | None,
        frameworks: list[str] | None,
        pattern: str,
        limit: int,
    ) -> list[KnowledgeUnit]:
        """Return approved units matching ``domains`` (already-normalised inside the repo)."""
        return await self._knowledge.query(
            domains,
            languages=languages,
            frameworks=frameworks,
            pattern=pattern,
            limit=limit,
        )

    async def stats(self) -> StatsResponse:
        """Return overall knowledge-store stats (totals, tiers, domains, confidence)."""
        return StatsResponse(
            total_count=await self._knowledge.count(),
            tier_counts=await self._knowledge.counts_by_tier(),
            domain_counts=await self._knowledge.domain_counts(),
            confidence_distribution=await self._knowledge.confidence_distribution(),
        )
