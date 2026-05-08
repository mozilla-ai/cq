"""Knowledge routes: query, propose, confirmations, flags, stats."""

from typing import Annotated

from cq.models import KnowledgeUnit
from fastapi import APIRouter, Query

from ...models.knowledge import FlagRequest, ProposeRequest, StatsResponse
from ..deps import APIKeyAuthDep, KnowledgeServiceDep

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("")
async def query_units(
    domains: Annotated[list[str], Query()],
    knowledge: KnowledgeServiceDep,
    languages: Annotated[list[str] | None, Query()] = None,
    frameworks: Annotated[list[str] | None, Query()] = None,
    pattern: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(gt=0)] = 5,
) -> list[KnowledgeUnit]:
    """Search knowledge units by domain tags with relevance ranking."""
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


@router.post("/{unit_id}/confirmations", status_code=201)
async def confirm_unit(
    unit_id: str,
    _username: APIKeyAuthDep,
    knowledge: KnowledgeServiceDep,
) -> KnowledgeUnit:
    """Confirm a knowledge unit, boosting its confidence."""
    return await knowledge.confirm(unit_id)


@router.post("/{unit_id}/flags", status_code=201)
async def flag_unit(
    unit_id: str,
    request: FlagRequest,
    _username: APIKeyAuthDep,
    knowledge: KnowledgeServiceDep,
) -> KnowledgeUnit:
    """Flag a knowledge unit, reducing its confidence."""
    return await knowledge.flag(unit_id, request.reason)


@router.get("/stats")
async def stats(knowledge: KnowledgeServiceDep) -> StatsResponse:
    """Return store statistics."""
    return await knowledge.stats()
