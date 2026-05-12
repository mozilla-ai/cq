"""Review service: queue, approve/reject decisions, dashboard stats."""

from __future__ import annotations

from ..exceptions import KnowledgeUnitAlreadyReviewedError, KnowledgeUnitNotFoundError
from ..models.review import (
    DailyCount,
    ReviewDecisionResponse,
    ReviewItem,
    ReviewQueueResponse,
    ReviewStatsResponse,
    TrendsResponse,
)
from ..repositories import KnowledgeRepository, ReviewRepository


class ReviewService:
    """Compose review-status transitions with knowledge-unit lookups."""

    def __init__(
        self,
        *,
        reviews: ReviewRepository,
        knowledge: KnowledgeRepository,
    ) -> None:
        """Compose the service over its repositories."""
        self._reviews = reviews
        self._knowledge = knowledge

    async def approve(self, unit_id: str, reviewer: str) -> ReviewDecisionResponse:
        """Approve a pending KU; raises 404 if missing, 409 if already reviewed."""
        return await self._decide(unit_id, "approved", reviewer)

    async def get_unit(self, unit_id: str) -> ReviewItem:
        """Return a single unit + review metadata; raises 404 if unknown."""
        ku = await self._knowledge.get_any(unit_id)
        if ku is None:
            raise KnowledgeUnitNotFoundError()
        review = await self._reviews.get_status(unit_id)
        assert review is not None  # Unit exists; get_any just returned it.
        return ReviewItem(
            knowledge_unit=ku,
            status=review["status"] or "pending",
            reviewed_by=review["reviewed_by"],
            reviewed_at=review["reviewed_at"],
        )

    async def list_units(
        self,
        *,
        domain: str | None = None,
        confidence_min: float | None = None,
        confidence_max: float | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ReviewItem]:
        """Return units filtered by domain, confidence range, and status."""
        items = await self._reviews.list_units(
            domain=domain,
            confidence_min=confidence_min,
            confidence_max=confidence_max,
            status=status,
            limit=limit,
        )
        return [
            ReviewItem(
                knowledge_unit=item["knowledge_unit"],
                status=item["status"],
                reviewed_by=item["reviewed_by"],
                reviewed_at=item["reviewed_at"],
            )
            for item in items
        ]

    async def queue(self, *, limit: int = 20, offset: int = 0) -> ReviewQueueResponse:
        """Return a page of pending KUs together with the total pending count."""
        items = await self._reviews.pending_queue(limit=limit, offset=offset)
        total = await self._reviews.pending_count()
        return ReviewQueueResponse(
            items=[
                ReviewItem(
                    knowledge_unit=item["knowledge_unit"],
                    status=item["status"],
                    reviewed_by=item["reviewed_by"],
                    reviewed_at=item["reviewed_at"],
                )
                for item in items
            ],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def reject(self, unit_id: str, reviewer: str) -> ReviewDecisionResponse:
        """Reject a pending KU; raises 404 if missing, 409 if already reviewed."""
        return await self._decide(unit_id, "rejected", reviewer)

    async def stats(self) -> ReviewStatsResponse:
        """Return dashboard metrics: counts, domains, confidence buckets, activity, trends."""
        counts = await self._reviews.counts_by_status()
        return ReviewStatsResponse(
            counts={
                "pending": counts.get("pending", 0),
                "approved": counts.get("approved", 0),
                "rejected": counts.get("rejected", 0),
            },
            domains=await self._knowledge.domain_counts(),
            confidence_distribution=await self._reviews.confidence_distribution(),
            recent_activity=await self._reviews.recent_activity(),
            trends=TrendsResponse(
                daily=[DailyCount(**d) for d in await self._reviews.daily_counts()],
            ),
        )

    async def _decide(self, unit_id: str, status: str, reviewer: str) -> ReviewDecisionResponse:
        """Apply ``status`` (``"approved"`` / ``"rejected"``) to a pending unit."""
        existing = await self._reviews.get_status(unit_id)
        if existing is None:
            raise KnowledgeUnitNotFoundError()
        existing_status = existing["status"] or "pending"
        if existing_status != "pending":
            raise KnowledgeUnitAlreadyReviewedError(existing_status)
        await self._reviews.set_status(unit_id, status, reviewer)
        updated = await self._reviews.get_status(unit_id)
        assert updated is not None  # Unit exists; we just wrote to it.
        st = updated["status"]
        rb = updated["reviewed_by"]
        ra = updated["reviewed_at"]
        assert st is not None
        assert rb is not None
        assert ra is not None
        return ReviewDecisionResponse(unit_id=unit_id, status=st, reviewed_by=rb, reviewed_at=ra)
