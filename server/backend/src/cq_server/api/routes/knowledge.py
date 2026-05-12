"""Knowledge routes: query, propose, confirmations, flags, stats."""

from typing import Annotated

from cq.models import KnowledgeUnit
from fastapi import APIRouter, Query, status

from ...exceptions import InvalidDomainError, KnowledgeUnitNotFoundError, ServiceError
from ...models.knowledge import FlagRequest, ProposeRequest, StatsResponse
from ..deps import APIKeyAuthDep, KnowledgeServiceDep

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def knowledge_exception_mappings() -> dict[type[ServiceError], int]:
    """Return service-exception to HTTP-status mappings for knowledge routes."""
    return {
        InvalidDomainError: status.HTTP_422_UNPROCESSABLE_CONTENT,
        KnowledgeUnitNotFoundError: status.HTTP_404_NOT_FOUND,
    }


@router.get("", response_model_exclude={"__all__": {"created_by"}})
async def query_units(
    domains: Annotated[list[str], Query()],
    knowledge: KnowledgeServiceDep,
    languages: Annotated[list[str] | None, Query()] = None,
    frameworks: Annotated[list[str] | None, Query()] = None,
    pattern: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(gt=0)] = 5,
) -> list[KnowledgeUnit]:
    """Search knowledge units by domain tags with relevance ranking.

    ``created_by`` is excluded from query responses to avoid leaking personal
    identifiers through the public read path until user-level attribution
    opt-in semantics are implemented.
    """
    return await knowledge.query(
        domains=domains,
        languages=languages,
        frameworks=frameworks,
        pattern=pattern or "",
        limit=limit,
    )


@router.post("", status_code=201)
async def propose_unit(
    request: ProposeRequest,
    username: APIKeyAuthDep,
    knowledge: KnowledgeServiceDep,
) -> KnowledgeUnit:
    """Submit a new knowledge unit.

    ``created_by`` is always set to the authenticated caller's username; any
    value supplied by the client is discarded.
    """
    return await knowledge.propose(
        domains=request.domains,
        insight=request.insight,
        context=request.context,
        created_by=username,
    )


@router.post("/{unit_id}/confirmations", status_code=201, response_model_exclude={"created_by"})
async def confirm_unit(
    unit_id: str,
    _username: APIKeyAuthDep,
    knowledge: KnowledgeServiceDep,
) -> KnowledgeUnit:
    """Confirm a knowledge unit, boosting its confidence.

    ``created_by`` is excluded to avoid exposing proposer identity through
    API responses until explicit attribution opt-in exists.
    """
    return await knowledge.confirm(unit_id)


@router.post("/{unit_id}/flags", status_code=201, response_model_exclude={"created_by"})
async def flag_unit(
    unit_id: str,
    request: FlagRequest,
    _username: APIKeyAuthDep,
    knowledge: KnowledgeServiceDep,
) -> KnowledgeUnit:
    """Flag a knowledge unit, reducing its confidence.

    ``created_by`` is excluded to avoid exposing proposer identity through
    API responses until explicit attribution opt-in exists.
    """
    return await knowledge.flag(unit_id, request.reason)


@router.get("/stats")
async def stats(knowledge: KnowledgeServiceDep) -> StatsResponse:
    """Return store statistics."""
    return await knowledge.stats()
