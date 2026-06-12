"""Pydantic schemas for /knowledge routes."""

from cq.models import Context, FlagReason, Insight, KnowledgeUnit
from pydantic import BaseModel, Field


class FlagRequest(BaseModel):
    """Request body for flagging a knowledge unit."""

    reason: FlagReason


class KnowledgeUnitList(BaseModel):
    """Unpaginated collection envelope for knowledge unit listings.

    NOTE: List is the unpaginated shape (``{data: [...]}``); cursor-paginated
    endpoints use a separate ``Page`` model. See docs/architecture.md §6.
    """

    data: list[KnowledgeUnit]


class ProposeRequest(BaseModel):
    """Request body for proposing a new knowledge unit."""

    domains: list[str] = Field(min_length=1)
    insight: Insight
    context: Context = Field(default_factory=Context)
    created_by: str = ""


class StatsResponse(BaseModel):
    """Response body for store statistics.

    Field names follow the canonical ``StoreStats`` wire vocabulary shared
    with the SDK clients; renaming them is a breaking wire change.

    NOTE: ``confidence_distribution`` covers the units this store reports to
    the caller (their private/org tier), not the public commons. Clients merge
    it with their local distribution and label the combined scope accordingly.
    """

    total_count: int
    tier_counts: dict[str, int]
    domain_counts: dict[str, int]
    confidence_distribution: dict[str, int]
