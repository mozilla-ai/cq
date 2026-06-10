"""cq knowledge store API."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from .api.routes.auth import auth_exception_mappings
from .api.routes.auth import router as auth_router
from .api.routes.knowledge import knowledge_exception_mappings
from .api.routes.knowledge import router as knowledge_router
from .api.routes.review import review_exception_mappings
from .api.routes.review import router as review_router
from .api.routes.users import router as users_router
from .api.routes.users import user_exception_mappings
from .core.config import Settings
from .core.db import Database
from .exceptions import ServiceError
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

_exception_mappings: dict[type[ServiceError], int] = {
    **auth_exception_mappings(),
    **knowledge_exception_mappings(),
    **review_exception_mappings(),
    **user_exception_mappings(),
}


@app.exception_handler(ServiceError)
async def service_error_handler(_request: Request, exc: ServiceError) -> JSONResponse:
    """Translate known service exceptions into HTTP responses."""
    status_code = _exception_mappings.get(type(exc), 500)
    return JSONResponse(status_code=status_code, content={"detail": exc.message})


# Mount API routes only at /api/v1; the previous root mount has been
# removed so versioning is unambiguous and clients always route through
# the same prefix.
app.include_router(api_router, prefix="/api/v1")


@app.get("/.well-known/cq-node.json", include_in_schema=False)
def well_known_cq_node() -> None:
    """Decline to publish a node discovery document.

    A 404 here tells cq clients to use defaults (api_base_url at
    {addr}/api/v1, api_version=v1). Registered explicitly at the app
    level so the SPA catch-all does not intercept the well-known path
    and return text/html when the combined frontend image is in use.
    Operators who want to advertise a custom api_base_url should serve
    /.well-known/cq-node.json from a reverse proxy in front of this
    server instead of generating it from inside the application.
    """
    raise HTTPException(status_code=404, detail="Not Found")


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
