"""cq knowledge store API."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import uvicorn
from cq.models import (
    Context,
    FlagReason,
    Insight,
    KnowledgeUnit,
    Tier,
    create_knowledge_unit,
)
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import FileResponse

from .auth import router as auth_router
from .deps import API_KEY_PEPPER_ENV, require_api_key
from .review import router as review_router
from .scoring import apply_confirmation, apply_flag
from .store import RemoteStore, normalize_domains

_STATIC_DIR = Path(__file__).parent / "static"


class ProposeRequest(BaseModel):
    """Request body for proposing a new knowledge unit."""

    domains: list[str] = Field(min_length=1)
    insight: Insight
    context: Context = Field(default_factory=Context)
    created_by: str = ""


class FlagRequest(BaseModel):
    """Request body for flagging a knowledge unit."""

    reason: FlagReason


class StatsResponse(BaseModel):
    """Response body for store statistics."""

    total_units: int
    tiers: dict[str, int]
    domains: dict[str, int]


_store: RemoteStore | None = None


def _get_store() -> RemoteStore:
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
    pepper = os.environ.get(API_KEY_PEPPER_ENV, "")
    if not pepper:
        raise RuntimeError(f"{API_KEY_PEPPER_ENV} environment variable is required")
    db_path = Path(os.environ.get("CQ_DB_PATH", "/data/cq.db"))
    _store = RemoteStore(db_path=db_path)
    app_instance.state.store = _store
    app_instance.state.api_key_pepper = pepper
    yield
    _store.close()


# --- API routes on a shared router so they can be mounted at both / and /api. ---

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(review_router)


@api_router.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@api_router.get("/query")
def query_units(
    domains: Annotated[list[str], Query()],
    languages: Annotated[list[str] | None, Query()] = None,
    frameworks: Annotated[list[str] | None, Query()] = None,
    pattern: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(gt=0)] = 5,
) -> list[KnowledgeUnit]:
    """Search knowledge units by domain tags with relevance ranking."""
    store = _get_store()
    return store.query(
        domains,
        languages=languages,
        frameworks=frameworks,
        pattern=pattern or "",
        limit=limit,
    )


@api_router.post("/propose", status_code=201)
def propose_unit(
    request: ProposeRequest,
    username: str = Depends(require_api_key),
) -> KnowledgeUnit:
    """Submit a new knowledge unit.

    ``created_by`` is always set to the authenticated caller's username; any
    value supplied by the client is discarded.
    """
    store = _get_store()
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
    store.insert(unit)
    return unit


@api_router.post("/confirm/{unit_id}")
def confirm_unit(unit_id: str, _username: str = Depends(require_api_key)) -> KnowledgeUnit:
    """Confirm a knowledge unit, boosting its confidence."""
    store = _get_store()
    unit = store.get(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Knowledge unit not found")
    confirmed = apply_confirmation(unit)
    store.update(confirmed)
    return confirmed


@api_router.post("/flag/{unit_id}")
def flag_unit(unit_id: str, request: FlagRequest, _username: str = Depends(require_api_key)) -> KnowledgeUnit:
    """Flag a knowledge unit, reducing its confidence."""
    store = _get_store()
    unit = store.get(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Knowledge unit not found")
    flagged = apply_flag(unit, request.reason)
    store.update(flagged)
    return flagged


@api_router.get("/stats")
def stats() -> StatsResponse:
    """Return store statistics."""
    store = _get_store()
    return StatsResponse(
        total_units=store.count(),
        tiers=store.counts_by_tier(),
        domains=store.domain_counts(),
    )


# --- Application assembly. ---

app = FastAPI(title="cq Server", version="0.1.0", lifespan=lifespan)

# Mount API routes at root (SDK compatibility) and at /api (frontend).
app.include_router(api_router)
app.include_router(api_router, prefix="/api/v1")

# Serve the frontend static build when present (combined Docker image).
if _STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa_fallback(path: str) -> FileResponse:
        """Serve the SPA entry point for any unmatched path."""
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(_STATIC_DIR / "index.html")


def main() -> None:
    """Start the cq API server."""
    port = int(os.environ.get("CQ_PORT", "3000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
