"""cq knowledge store API."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from .api.routes.auth import router as auth_router
from .api.routes.knowledge import router as knowledge_router
from .api.routes.review import router as review_router
from .api.routes.users import router as users_router
from .core.config import Settings
from .core.db import Database
from .migrations import run_migrations

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    """Load configuration, run migrations, and own the database lifecycle."""
    # ``Settings`` raises a ValidationError if either secret is unset, so
    # the lifespan fails fast with a clear message instead of crashing
    # later at first request.
    # Fields populated from CQ_* env vars; the static type checker can't see that.
    settings = Settings()  # ty: ignore[missing-argument]
    # Single URL feeds both the database wrapper and the migration runner,
    # so they can't diverge on which database they target. Build the
    # ``Database`` first so a Postgres URL surfaces ``NotImplementedError``
    # (#311/#312 guidance) instead of failing inside Alembic with a raw
    # psycopg ``ModuleNotFoundError``.
    database = Database(settings)
    # Close the database if migrations fail — otherwise its engine and
    # SQLite file handle leak across in-process lifespan re-entries
    # (tests, restart loops). The post-yield ``finally`` only covers
    # successful boots.
    try:
        # See ``cq_server.migrations.run_migrations`` for the
        # three-case startup contract.
        run_migrations(settings.resolved_database_url)
    except BaseException:
        await database.close()
        raise
    app_instance.state.settings = settings
    app_instance.state.database = database
    try:
        yield
    finally:
        await database.close()


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
