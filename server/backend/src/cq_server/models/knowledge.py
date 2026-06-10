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
    """Response body for store statistics."""

    total_units: int
    tiers: dict[str, int]
    domains: dict[str, int]
