"""Review queue endpoints for the review API."""

from fastapi import APIRouter

from ...models.review import (
    ReviewDecisionResponse,
    ReviewItem,
    ReviewQueueResponse,
    ReviewStatsResponse,
)
from ..deps import CurrentUserDep, ReviewServiceDep

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/queue")
async def review_queue(
    _user: CurrentUserDep,
    reviews: ReviewServiceDep,
    limit: int = 20,
    offset: int = 0,
) -> ReviewQueueResponse:
    """Return pending KUs for review."""
    return await reviews.queue(limit=limit, offset=offset)


@router.post("/{unit_id}/approve")
async def approve_unit(
    unit_id: str,
    username: CurrentUserDep,
    reviews: ReviewServiceDep,
) -> ReviewDecisionResponse:
    """Approve a pending KU."""
    return await reviews.approve(unit_id, username)


@router.post("/{unit_id}/reject")
async def reject_unit(
    unit_id: str,
    username: CurrentUserDep,
    reviews: ReviewServiceDep,
) -> ReviewDecisionResponse:
    """Reject a pending KU."""
    return await reviews.reject(unit_id, username)


@router.get("/stats")
async def review_stats(
    _user: CurrentUserDep,
    reviews: ReviewServiceDep,
) -> ReviewStatsResponse:
    """Return dashboard metrics."""
    return await reviews.stats()


@router.get("/units")
async def list_units(
    _user: CurrentUserDep,
    reviews: ReviewServiceDep,
    domain: str | None = None,
    confidence_min: float | None = None,
    confidence_max: float | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[ReviewItem]:
    """Return KUs filtered by domain, confidence range, or status."""
    return await reviews.list_units(
        domain=domain,
        confidence_min=confidence_min,
        confidence_max=confidence_max,
        status=status,
        limit=limit,
    )


@router.get("/{unit_id}")
async def get_unit(
    unit_id: str,
    _user: CurrentUserDep,
    reviews: ReviewServiceDep,
) -> ReviewItem:
    """Return a single knowledge unit with its review metadata."""
    return await reviews.get_unit(unit_id)
