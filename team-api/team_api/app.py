"""cq team knowledge store API."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import router as auth_router
from .review import router as review_router
from .knowledge_unit import (
    Context,
    Evidence,
    FlagReason,
    Insight,
    KnowledgeUnit,
    Tier,
    create_knowledge_unit,
)
from .scoring import apply_confirmation, apply_flag
from .store import TeamStore, normalise_domains


class ProposeRequest(BaseModel):
    """Request body for proposing a new knowledge unit."""

    id: str | None = None
    domain: list[str] = Field(min_length=1)
    insight: Insight
    context: Context = Field(default_factory=Context)
    evidence: Evidence | None = None
    created_by: str = ""


class FlagRequest(BaseModel):
    """Request body for flagging a knowledge unit."""

    reason: FlagReason


class StatsResponse(BaseModel):
    """Response body for store statistics."""

    total_units: int
    domains: dict[str, int]


_store: TeamStore | None = None


def _get_store() -> TeamStore:
    """Return the global store instance."""
    if _store is None:
        raise RuntimeError("Store not initialised")
    return _store


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    """Manage the store lifecycle."""
    global _store  # noqa: PLW0603
    jwt_secret = os.environ.get("CQ_JWT_SECRET")
    if not jwt_secret:
        raise RuntimeError("CQ_JWT_SECRET environment variable is required")
    db_path = Path(os.environ.get("CQ_DB_PATH", "/data/team.db"))
    _store = TeamStore(db_path=db_path)
    app_instance.state.store = _store
    yield
    _store.close()


app = FastAPI(title="cq Team API", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(review_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/query")
def query_units(
    domain: Annotated[list[str], Query()],
    language: Annotated[str | None, Query()] = None,
    framework: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(gt=0)] = 5,
) -> list[KnowledgeUnit]:
    """Search knowledge units by domain tags with relevance ranking."""
    store = _get_store()
    return store.query(domain, language=language, framework=framework, limit=limit)


@app.post("/propose", status_code=201)
def propose_unit(request: ProposeRequest) -> KnowledgeUnit:
    """Submit a new knowledge unit to the team store."""
    store = _get_store()
    domains = normalise_domains(request.domain)
    if not domains:
        raise HTTPException(
            status_code=422, detail="At least one non-empty domain is required"
        )
    if request.id is None and request.evidence is None:
        unit = create_knowledge_unit(
            domain=domains,
            insight=request.insight,
            context=request.context,
            tier=Tier.TEAM,
            created_by=request.created_by,
        )
    else:
        unit = KnowledgeUnit(
            id=request.id or create_knowledge_unit(domain=domains, insight=request.insight).id,
            domain=domains,
            insight=request.insight,
            context=request.context,
            evidence=request.evidence or Evidence(),
            tier=Tier.TEAM,
            created_by=request.created_by,
        )
    store.insert(unit)
    return unit


@app.post("/confirm/{unit_id}")
def confirm_unit(unit_id: str) -> KnowledgeUnit:
    """Confirm a knowledge unit, boosting its confidence."""
    store = _get_store()
    unit = store.get(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Knowledge unit not found")
    confirmed = apply_confirmation(unit)
    store.update(confirmed)
    return confirmed


@app.post("/flag/{unit_id}")
def flag_unit(unit_id: str, request: FlagRequest) -> KnowledgeUnit:
    """Flag a knowledge unit, reducing its confidence."""
    store = _get_store()
    unit = store.get(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Knowledge unit not found")
    flagged = apply_flag(unit, request.reason)
    store.update(flagged)
    return flagged


@app.get("/stats")
def stats() -> StatsResponse:
    """Return store statistics."""
    store = _get_store()
    return StatsResponse(
        total_units=store.count(),
        domains=store.domain_counts(),
    )


def main() -> None:
    """Start the cq team API server."""
    uvicorn.run(app, host="0.0.0.0", port=8742)
