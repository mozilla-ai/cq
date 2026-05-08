"""cq knowledge store API."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from .api.deps import API_KEY_PEPPER_ENV
from .api.routes.auth import router as auth_router
from .api.routes.knowledge import router as knowledge_router
from .api.routes.review import router as review_router
from .api.routes.users import router as users_router
from .db_url import resolve_database_url
from .migrations import run_migrations
from .store import Store, create_store

_STATIC_DIR = Path(__file__).parent / "static"

_store: Store | None = None


def _get_store() -> Store:
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
    # Single URL feeds both the store factory and the migration runner,
    # so they can't diverge on which database they target. Run the
    # factory first so a Postgres URL surfaces ``NotImplementedError``
    # (#311/#312 guidance) instead of failing inside Alembic with a
    # raw psycopg ``ModuleNotFoundError``.
    database_url = resolve_database_url()
    new_store = create_store(database_url)
    # Close ``new_store`` if migrations fail — otherwise its engine and
    # SQLite file handle leak across in-process lifespan re-entries
    # (tests, restart loops). The post-yield ``finally`` only covers
    # successful boots.
    try:
        # See ``cq_server.migrations.run_migrations`` for the
        # three-case startup contract.
        run_migrations(database_url)
    except BaseException:
        await new_store.close()
        raise
    # Assign the global only after both startup steps succeed, so a
    # failure mid-boot doesn't leave a half-initialised ``_store``
    # leaking from the previous lifespan (matters when tests re-enter
    # ``lifespan`` in-process after a startup failure).
    _store = new_store
    app_instance.state.store = _store
    app_instance.state.api_key_pepper = pepper
    try:
        yield
    finally:
        await _store.close()


# --- API assembly: every domain router under /api/v1. ---

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(knowledge_router)
api_router.include_router(review_router)


@api_router.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


# --- Application assembly. ---

app = FastAPI(title="cq Server", version="0.1.0", lifespan=lifespan)

# Mount API routes only at /api/v1; the previous root mount has been
# removed so versioning is unambiguous and clients always route through
# the same prefix.
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
