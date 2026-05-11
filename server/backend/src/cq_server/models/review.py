"""Pydantic schemas for /review routes."""

from cq.models import KnowledgeUnit
from pydantic import BaseModel


class DailyCount(BaseModel):
    """Daily proposal, approval, and rejection counts."""

    date: str
    proposed: int
    approved: int
    rejected: int


class ReviewDecisionResponse(BaseModel):
    """Response after approving or rejecting a KU."""

    unit_id: str
    status: str
    reviewed_by: str
    reviewed_at: str


class ReviewItem(BaseModel):
    """A KU with its review metadata."""

    knowledge_unit: KnowledgeUnit
    status: str
    reviewed_by: str | None
    reviewed_at: str | None


class ReviewQueueResponse(BaseModel):
    """Paginated review queue response."""

    items: list[ReviewItem]
    total: int
    offset: int
    limit: int


class TrendsResponse(BaseModel):
    """Trend data for the dashboard chart."""

    daily: list[DailyCount]


class ReviewStatsResponse(BaseModel):
    """Dashboard metrics response."""

    counts: dict[str, int]
    domains: dict[str, int]
    confidence_distribution: dict[str, int]
    recent_activity: list[dict]
    trends: TrendsResponse
