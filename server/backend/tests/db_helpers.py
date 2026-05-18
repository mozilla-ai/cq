"""Shared DB-setup helpers for cq-server backend tests.

Schema is owned by Alembic — tests that touch the database must run
``run_migrations`` against the file before instantiating ``SqliteStore``.
``init_test_db`` is a one-line wrapper for that idiom.

``build_pre_alembic_schema`` synthesises a legacy production-shape DB
(without an ``alembic_version`` row) so the migration tests can verify
the stamp-on-legacy case.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
import pytest_asyncio

from cq_server.migrations import run_migrations
from cq_server.core.config import Settings
from cq_server.core.db import Database
from cq_server.repositories import (
    APIKeyRepository,
    KnowledgeRepository,
    ReviewRepository,
    UserRepository,
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


def sqlite_url(db: Path) -> str:
    """Return the ``sqlite:///`` URL for a filesystem path."""
    return f"sqlite:///{db}"


def init_test_db(db: Path) -> None:
    """Create the schema in ``db`` via the production Alembic runner."""
    run_migrations(sqlite_url(db))


def _make_store(db_path: Path) -> _RepoBundle:
    """Build a fresh ``_RepoBundle`` for a single test.

    Equivalent to the historical ``SqliteStore(db_path=...)`` construction;
    just routed through the decomposed ``Database`` + repository layout.
    """
    settings = Settings(  # type: ignore[call-arg]
        jwt_secret="test-jwt-secret",  # pragma: allowlist secret
        api_key_pepper="test-pepper",  # pragma: allowlist secret
        database_url=f"sqlite:///{db_path}",
        db_path=db_path,
    )
    return _RepoBundle(Database(settings))


# Historical pre-Alembic schema, reproduced here as one frozen artifact
# so ``TestExistingPreAlembicDatabase`` can synthesise a legacy
# production DB without depending on the deleted runtime DDL. **Do not
# split into reusable building blocks** — the whole point is that this
# is one immutable snapshot of the pre-Alembic schema (the union of
# what ``_ensure_schema`` + ``ensure_review_columns`` +
# ``ensure_users_table`` + ``ensure_api_keys_table`` used to emit, in
# that order). Anything that wants to reuse a fragment of this should
# instead initialise via ``init_test_db`` (Alembic owns the schema
# now).
_PRE_ALEMBIC_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS knowledge_units (
        id TEXT PRIMARY KEY,
        data TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS knowledge_unit_domains (
        unit_id TEXT NOT NULL,
        domain TEXT NOT NULL,
        FOREIGN KEY (unit_id) REFERENCES knowledge_units(id) ON DELETE CASCADE,
        PRIMARY KEY (unit_id, domain)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_domains_domain ON knowledge_unit_domains(domain)",
    "ALTER TABLE knowledge_units ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'",
    "ALTER TABLE knowledge_units ADD COLUMN reviewed_by TEXT",
    "ALTER TABLE knowledge_units ADD COLUMN reviewed_at TEXT",
    "ALTER TABLE knowledge_units ADD COLUMN created_at TEXT",
    "ALTER TABLE knowledge_units ADD COLUMN tier TEXT NOT NULL DEFAULT 'private'",
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS api_keys (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        labels TEXT NOT NULL DEFAULT '[]',
        key_prefix TEXT NOT NULL,
        key_hash TEXT NOT NULL UNIQUE,
        ttl TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_used_at TEXT,
        revoked_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id)",
)


def build_pre_alembic_schema(db: Path) -> None:
    """Build a production-shape SQLite DB *without* an alembic_version row.

    Reproduces the historical schema that the legacy ``_ensure_schema``
    + ``ensure_*`` startup path used to produce, so the migration tests
    can verify the stamp-on-legacy-DB case without resurrecting deleted
    code. Connection settings (``foreign_keys = ON``) match the
    pragmas applied at runtime.

    Raises ``FileExistsError`` if ``db`` already exists: the
    ``ALTER TABLE … ADD COLUMN`` statements in
    ``_PRE_ALEMBIC_STATEMENTS`` are not idempotent, and the deep
    ``sqlite3.OperationalError: duplicate column name`` you'd get
    otherwise is harder to trace back to the misuse.
    """
    if db.exists():
        raise FileExistsError(f"build_pre_alembic_schema requires a fresh path; got existing {db}")
    conn = sqlite3.connect(str(db))
    try:
        with conn:
            conn.execute("PRAGMA foreign_keys = ON")
            for stmt in _PRE_ALEMBIC_STATEMENTS:
                conn.execute(stmt)
    finally:
        conn.close()
