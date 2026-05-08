"""Knowledge routes: query, propose, confirmations, flags, stats."""

from typing import Annotated

from cq.models import KnowledgeUnit, Tier, create_knowledge_unit
from fastapi import APIRouter, Depends, HTTPException, Query

from ...models.knowledge import FlagRequest, ProposeRequest, StatsResponse
from ...scoring import apply_confirmation, apply_flag
from ...store import Store, normalize_domains
from ..deps import get_store, require_api_key

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("")
async def query_units(
    domains: Annotated[list[str], Query()],
    languages: Annotated[list[str] | None, Query()] = None,
    frameworks: Annotated[list[str] | None, Query()] = None,
    pattern: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(gt=0)] = 5,
    store: Store = Depends(get_store),
) -> list[KnowledgeUnit]:
    """Search knowledge units by domain tags with relevance ranking."""
    return await store.query(
        domains,
        languages=languages,
        frameworks=frameworks,
        pattern=pattern or "",
        limit=limit,
    )


@router.post("", status_code=201)
async def propose_unit(
    request: ProposeRequest,
    username: str = Depends(require_api_key),
    store: Store = Depends(get_store),
) -> KnowledgeUnit:
    """Submit a new knowledge unit.

    ``created_by`` is always set to the authenticated caller's username; any
    value supplied by the client is discarded.
    """
    normalized = normalize_domains(request.domains)
    if not normalized:
        raise HTTPException(status_code=422, detail="At least one non-empty domain is required")
    unit = create_knowledge_unit(
        domains=normalized,
        insight=request.insight,
        context=request.context,
        tier=Tier.PRIVATE,
        created_by=username,
    )
    await store.insert(unit)
    return unit


@router.post("/{unit_id}/confirmations", status_code=201)
async def confirm_unit(
    unit_id: str,
    _username: str = Depends(require_api_key),
    store: Store = Depends(get_store),
) -> KnowledgeUnit:
    """Confirm a knowledge unit, boosting its confidence."""
    unit = await store.get(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Knowledge unit not found")
    confirmed = apply_confirmation(unit)
    await store.update(confirmed)
    return confirmed


@router.post("/{unit_id}/flags", status_code=201)
async def flag_unit(
    unit_id: str,
    request: FlagRequest,
    _username: str = Depends(require_api_key),
    store: Store = Depends(get_store),
) -> KnowledgeUnit:
    """Flag a knowledge unit, reducing its confidence."""
    unit = await store.get(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Knowledge unit not found")
    flagged = apply_flag(unit, request.reason)
    await store.update(flagged)
    return flagged


@router.get("/stats")
async def stats(
    store: Store = Depends(get_store),
) -> StatsResponse:
    """Return store statistics."""
    return StatsResponse(
        total_units=await store.count(),
        tiers=await store.counts_by_tier(),
        domains=await store.domain_counts(),
    )
