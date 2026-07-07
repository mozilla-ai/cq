"""Shared test fixtures for the cq-server backend.

Tests at the repository layer take the typed ``users_repo`` /
``api_keys_repo`` / ``knowledge_repo`` / ``reviews_repo`` fixtures
directly. Tests inherited from the pre-decomposition era can take the
``repos`` fixture, which exposes all four repositories on a single
``SimpleNamespace`` plus a ``close()`` method, mirroring the shape of
the old ``Store`` while delegating to the new repositories.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import text

from cq_server.core.config import Settings
from cq_server.core.db import Database
from cq_server.migrations import run_migrations
from cq_server.repositories import (
    APIKeyRepository,
    KnowledgeRepository,
    ReviewRepository,
    UserRepository,
)

from .db_helpers import _RepoBundle, init_test_db

# Configure basic logging to ensure DEBUG level logs are output to the console
logging.basicConfig(level=logging.DEBUG)

# Configure SQLAlchemy logging
logging.getLogger("sqlalchemy.engine").setLevel(logging.DEBUG)
logging.getLogger("sqlalchemy.orm").setLevel(logging.DEBUG)
logging.getLogger("sqlalchemy.dialects").setLevel(logging.DEBUG)
logging.getLogger("cq_server.semsearch").setLevel(logging.DEBUG)
logging.getLogger("cq_server.semsearch.queries").setLevel(logging.DEBUG)
logging.getLogger("cq_server.repositories").setLevel(logging.DEBUG)


def _build_settings(db_path: Path) -> Settings:
    """
    Create a Settings instance configured for tests.

    Parameters:
        db_path (Path): Filesystem path to the SQLite database file used by tests.

    Returns:
        Settings: A Settings object with test secrets and a `sqlite:///` database URL pointing to `db_path`.
    """
    return Settings(  # type: ignore[call-arg]
        jwt_secret="test-jwt-secret",  # pragma: allowlist secret
        api_key_pepper="test-pepper",  # pragma: allowlist secret
        database_url=f"sqlite:///{db_path}",
        db_path=db_path,
    )


def _build_pg_settings(url: str) -> Settings:
    """Create a Settings instance pointed at the PostgreSQL container URL."""
    return Settings(  # type: ignore[call-arg]
        jwt_secret="test-jwt-secret",  # pragma: allowlist secret
        api_key_pepper="test-pepper",  # pragma: allowlist secret
        database_url=url,
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """
    Create a fresh SQLite database file at the test temporary path and initialize it with Alembic migrations.

    Returns:
        Path: Path to the created SQLite database file initialized with Alembic migrations.
    """
    db = tmp_path / "cq.db"
    init_test_db(db)
    return db


@pytest_asyncio.fixture
async def users_repo(repos: _RepoBundle) -> UserRepository:
    """
    Provide the UserRepository instance from the shared repository bundle.

    Parameters:
        repos (_RepoBundle): Shared bundle containing repository instances for tests.

    Returns:
        UserRepository: The repository used to access and manipulate user records.
    """
    return repos.users


@pytest_asyncio.fixture
async def api_keys_repo(repos: _RepoBundle) -> APIKeyRepository:
    """
    Provide the APIKeyRepository instance from the shared repository bundle.

    Returns:
        APIKeyRepository: The API key repository extracted from the provided `_RepoBundle`.
    """
    return repos.api_keys


@pytest_asyncio.fixture
async def knowledge_repo(repos: _RepoBundle) -> KnowledgeRepository:
    """
    Provide the KnowledgeRepository instance from the shared repository bundle.

    Parameters:
        repos (_RepoBundle): Shared repository bundle provided by the `repos` fixture.

    Returns:
        KnowledgeRepository: The knowledge repository from the bundle.
    """
    return repos.knowledge


@pytest_asyncio.fixture
async def reviews_repo(repos: _RepoBundle) -> ReviewRepository:
    """
    Provide the ReviewRepository from the shared repository bundle.

    Parameters:
        repos (_RepoBundle): Shared bundle containing repository instances used by tests.

    Returns:
        ReviewRepository: The review repository instance from the provided bundle.
    """
    return repos.reviews


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    """Start a session-scoped PostgreSQL container and yield its psycopg URL.

    Skips the whole PG suite when Docker is unavailable so the SQLite
    tests still run on a bare machine (see #312 DoD). Migrations run once
    against the fresh container; per-test isolation is handled by
    ``pg_repos`` truncating between tests.

    Not safe under ``pytest-xdist``: the container is shared session-wide,
    so a ``pg_repos`` TRUNCATE in one worker would clobber another worker's
    in-flight data. Give each xdist worker its own container before enabling
    parallel PG runs.
    """
    testcontainers = pytest.importorskip("testcontainers.postgres")
    try:
        container = testcontainers.PostgresContainer("postgres:16-alpine", driver="psycopg")
        container.start()
    except Exception as exc:  # noqa: BLE001 — Docker missing/unreachable
        pytest.skip(f"PostgreSQL container unavailable: {exc}")
    try:
        url = container.get_connection_url()
        run_migrations(url)
        yield url
    finally:
        container.stop()


@pytest_asyncio.fixture
async def pg_repos(pg_url: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_RepoBundle]:
    """Yield repositories wired to the PostgreSQL container, cleaned per test."""
    # These tests don't exercise semantic search; disable it so the PG suite
    # runs even when CI sets TOKEN_EMBEDDING_URL (which would otherwise trip
    # Database's semsearch-on-PG fail-fast guard).
    monkeypatch.setattr("cq_server.core.db._SEMSEARCH_ENABLED", False)
    db = Database(_build_pg_settings(pg_url))
    with db.engine.begin() as conn:
        conn.execute(text("TRUNCATE knowledge_units, knowledge_unit_domains, api_keys, users RESTART IDENTITY CASCADE"))
    bundle = _RepoBundle(db)
    try:
        yield bundle
    finally:
        await bundle.close()


@pytest_asyncio.fixture
async def repos(tmp_path: Path) -> AsyncIterator[_RepoBundle]:
    """Yield a bundle of all four repositories sharing one ``Database``.

    Useful for legacy tests inherited from the pre-decomposition era;
    new tests should prefer the per-repository fixtures.
    """
    db_path = tmp_path / "test.db"
    init_test_db(db_path)
    db = Database(_build_settings(db_path))
    bundle = _RepoBundle(db)
    try:
        yield bundle
    finally:
        await bundle.close()


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    """
    Provide a freshly migrated Database instance backed by a per-test SQLite file.

    Yields the Database for use by tests and ensures the connection is closed when the fixture is torn down.

    Returns:
        A Database connected to the migrated SQLite file at `tmp_path / "test.db"`.
    """
    db_path = tmp_path / "test.db"
    init_test_db(db_path)
    db = Database(_build_settings(db_path))
    try:
        yield db
    finally:
        await db.close()


# Re-export the namespace alias so legacy tests that imported the old
# ``SqliteStore`` symbol from ``conftest`` (rather than the production
# package) keep importing successfully. New code should use the typed
# repository fixtures.
__all__ = [
    "_RepoBundle",
    "api_keys_repo",
    "database",
    "knowledge_repo",
    "repos",
    "reviews_repo",
    "users_repo",
]


# pytest emits a SimpleNamespace-flavoured alias for tests that simply
# want a "store-like" object without caring about the underlying type.
StoreLike = SimpleNamespace
