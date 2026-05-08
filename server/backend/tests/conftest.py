"""Shared test fixtures for the cq-server backend.

Tests at the repository layer take the typed ``users_repo`` /
``api_keys_repo`` / ``knowledge_repo`` / ``reviews_repo`` fixtures
directly. Tests inherited from the pre-decomposition era can take the
``repos`` fixture, which exposes all four repositories on a single
``SimpleNamespace`` plus a ``close()`` method, mirroring the shape of
the old ``Store`` while delegating to the new repositories.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest_asyncio
from cq.models import KnowledgeUnit

from cq_server.core.config import Settings
from cq_server.core.db import Database
from cq_server.repositories import (
    APIKeyRepository,
    KnowledgeRepository,
    ReviewRepository,
    UserRepository,
)

from .db_helpers import init_test_db


def _build_settings(db_path: Path) -> Settings:
    """Construct ``Settings`` directly so tests don't depend on env state."""
    return Settings(  # type: ignore[call-arg]
        jwt_secret="test-jwt-secret",  # pragma: allowlist secret
        api_key_pepper="test-pepper",  # pragma: allowlist secret
        database_url=f"sqlite:///{db_path}",
        db_path=db_path,
    )


class _RepoBundle:
    """Lightweight container exposing the four repositories on a single object.

    Re-exposes the legacy ``Store`` surface as forwarding methods so that
    pre-decomposition tests can keep their ``store.<method>(...)`` calls
    while we migrate them piecemeal to per-repository fixtures. New tests
    should use the typed repository fixtures directly.
    """

    def __init__(self, db: Database) -> None:
        self._db = db
        self.users = UserRepository(db)
        self.api_keys = APIKeyRepository(db)
        self.knowledge = KnowledgeRepository(db)
        self.reviews = ReviewRepository(db)

    @property
    def _engine(self):
        """Expose the SQLAlchemy engine for tests that inspect schema directly."""
        return self._db.engine

    async def _run_sync(self, fn, /, *args, **kwargs):
        """Forward to ``Database.run_sync`` so legacy ``store._run_sync`` tests still work."""
        return await self._db.run_sync(fn, *args, **kwargs)

    async def close(self) -> None:
        await self._db.close()

    # --- Knowledge (legacy ``Store`` surface) ---

    async def count(self) -> int:
        return await self.knowledge.count()

    async def counts_by_tier(self) -> dict[str, int]:
        return await self.knowledge.counts_by_tier()

    async def domain_counts(self) -> dict[str, int]:
        return await self.knowledge.domain_counts()

    async def get(self, unit_id: str) -> KnowledgeUnit | None:
        return await self.knowledge.get(unit_id)

    async def get_any(self, unit_id: str) -> KnowledgeUnit | None:
        return await self.knowledge.get_any(unit_id)

    async def insert(self, unit: KnowledgeUnit) -> None:
        await self.knowledge.insert(unit)

    async def query(self, *args, **kwargs):
        return await self.knowledge.query(*args, **kwargs)

    async def update(self, unit: KnowledgeUnit) -> None:
        await self.knowledge.update(unit)

    # --- Reviews ---

    async def confidence_distribution(self):
        return await self.reviews.confidence_distribution()

    async def counts_by_status(self):
        return await self.reviews.counts_by_status()

    async def daily_counts(self, *args, **kwargs):
        return await self.reviews.daily_counts(*args, **kwargs)

    async def get_review_status(self, unit_id: str):
        return await self.reviews.get_status(unit_id)

    async def list_units(self, *args, **kwargs):
        return await self.reviews.list_units(*args, **kwargs)

    async def pending_count(self):
        return await self.reviews.pending_count()

    async def pending_queue(self, *args, **kwargs):
        return await self.reviews.pending_queue(*args, **kwargs)

    async def recent_activity(self, *args, **kwargs):
        return await self.reviews.recent_activity(*args, **kwargs)

    async def set_review_status(self, unit_id: str, status: str, reviewed_by: str) -> None:
        await self.reviews.set_status(unit_id, status, reviewed_by)

    # --- Users ---

    async def create_user(self, username: str, password_hash: str) -> None:
        await self.users.create(username, password_hash)

    async def get_user(self, username: str):
        return await self.users.get(username)

    # --- API keys ---

    async def count_active_api_keys_for_user(self, user_id: int) -> int:
        return await self.api_keys.count_active_for_user(user_id)

    async def create_api_key(self, *args, **kwargs):
        return await self.api_keys.create(*args, **kwargs)

    async def get_active_api_key_by_id(self, key_id: str):
        return await self.api_keys.get_active_by_id(key_id)

    async def get_api_key_for_user(self, *args, **kwargs):
        return await self.api_keys.get_for_user(*args, **kwargs)

    async def list_api_keys_for_user(self, user_id: int):
        return await self.api_keys.list_for_user(user_id)

    async def revoke_api_key(self, *args, **kwargs):
        return await self.api_keys.revoke(*args, **kwargs)

    async def touch_api_key_last_used(self, key_id: str) -> None:
        await self.api_keys.touch_last_used(key_id)


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    """Yield a freshly-migrated ``Database`` rooted at a per-test temp path."""
    db_path = tmp_path / "test.db"
    init_test_db(db_path)
    db = Database(_build_settings(db_path))
    try:
        yield db
    finally:
        await db.close()


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
async def users_repo(repos: _RepoBundle) -> UserRepository:
    """Yield the ``UserRepository`` from the shared bundle."""
    return repos.users


@pytest_asyncio.fixture
async def api_keys_repo(repos: _RepoBundle) -> APIKeyRepository:
    """Yield the ``APIKeyRepository`` from the shared bundle."""
    return repos.api_keys


@pytest_asyncio.fixture
async def knowledge_repo(repos: _RepoBundle) -> KnowledgeRepository:
    """Yield the ``KnowledgeRepository`` from the shared bundle."""
    return repos.knowledge


@pytest_asyncio.fixture
async def reviews_repo(repos: _RepoBundle) -> ReviewRepository:
    """Yield the ``ReviewRepository`` from the shared bundle."""
    return repos.reviews


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
