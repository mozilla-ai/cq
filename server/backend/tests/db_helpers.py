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

from cq.models import KnowledgeUnit

from cq_server.core.config import Settings
from cq_server.core.db import Database
from cq_server.migrations import run_migrations
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
        """
        Initialize the bundle with a Database and create per-domain repository instances.
        
        Stores the provided Database on self._db and constructs repository objects used by tests:
        self.users, self.api_keys, self.knowledge, and self.reviews.
        
        Parameters:
            db: Database — database instance used to create repository objects and accessed via self._db.
        """
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
        """
        Run a synchronous callable using the bundle's database context.
        
        Parameters:
            fn (Callable): A callable to execute synchronously against the database.
            *args: Positional arguments forwarded to `fn`.
            **kwargs: Keyword arguments forwarded to `fn`.
        
        Returns:
            The value returned by `fn`.
        """
        return await self._db.run_sync(fn, *args, **kwargs)

    async def close(self) -> None:
        """
        Close the underlying database connection and release associated resources.
        """
        await self._db.close()

    # --- Knowledge (legacy ``Store`` surface) ---

    async def count(self) -> int:
        """
        Return the total number of knowledge units in the database.
        
        Returns:
            int: The count of knowledge units.
        """
        return await self.knowledge.count()

    async def counts_by_tier(self) -> dict[str, int]:
        """
        Get counts of knowledge units grouped by tier.
        
        Returns:
            mapping (dict[str, int]): A mapping from tier name to the number of knowledge units in that tier.
        """
        return await self.knowledge.counts_by_tier()

    async def domain_counts(self) -> dict[str, int]:
        """
        Return counts of knowledge units grouped by domain.
        
        Returns:
            dict[str, int]: Mapping from domain name to the number of knowledge units for that domain.
        """
        return await self.knowledge.domain_counts()

    async def get(self, unit_id: str) -> KnowledgeUnit | None:
        """
        Fetches a knowledge unit by its identifier.
        
        Parameters:
            unit_id (str): The identifier of the knowledge unit to retrieve.
        
        Returns:
            KnowledgeUnit | None: `KnowledgeUnit` if a unit with the given id exists, `None` otherwise.
        """
        return await self.knowledge.get(unit_id)

    async def get_any(self, unit_id: str) -> KnowledgeUnit | None:
        """
        Retrieve a knowledge unit matching the given ID.
        
        Returns:
            The matching KnowledgeUnit if one exists, `None` otherwise.
        """
        return await self.knowledge.get_any(unit_id)

    async def insert(self, unit: KnowledgeUnit) -> None:
        """
        Insert the given knowledge unit into the underlying knowledge repository.
        
        Parameters:
            unit (KnowledgeUnit): The knowledge unit to persist.
        """
        await self.knowledge.insert(unit)

    async def query(self, *args, **kwargs):
        """
        Run a query against the knowledge store using the provided arguments.
        
        Parameters:
            *args: Positional arguments forwarded to the knowledge query implementation.
            **kwargs: Keyword arguments forwarded to the knowledge query implementation.
        
        Returns:
            The result produced by the knowledge query (type depends on the query and repository implementation).
        """
        return await self.knowledge.query(*args, **kwargs)

    async def update(self, unit: KnowledgeUnit) -> None:
        """
        Update an existing knowledge unit record in the database.
        
        Parameters:
            unit (KnowledgeUnit): The knowledge unit with updated fields; must correspond to an existing record in the database.
        """
        await self.knowledge.update(unit)

    # --- Reviews ---

    async def confidence_distribution(self):
        """
        Retrieve the distribution of review confidence scores.
        
        Returns:
            dict: Mapping of confidence level (typically an int or str) to count of reviews with that confidence.
        """
        return await self.reviews.confidence_distribution()

    async def counts_by_status(self):
        """
        Return counts of reviews grouped by status.
        
        Returns:
            dict[str, int]: Mapping from review status to its count.
        """
        return await self.reviews.counts_by_status()

    async def daily_counts(self, *args, **kwargs):
        """
        Return daily counts of reviews matching the provided filters.
        
        Parameters:
            *args: Positional arguments forwarded to the underlying reviews repository.
            **kwargs: Keyword arguments forwarded to the underlying reviews repository (e.g., filters, date range, grouping options).
        
        Returns:
            A sequence of (date, count) pairs representing the number of reviews for each day that match the provided filters.
        """
        return await self.reviews.daily_counts(*args, **kwargs)

    async def get_review_status(self, unit_id: str):
        """
        Retrieve the review status for a knowledge unit.
        
        Parameters:
        	unit_id (str): ID of the knowledge unit to query.
        
        Returns:
        	The review status of the specified knowledge unit.
        """
        return await self.reviews.get_status(unit_id)

    async def list_units(self, *args, **kwargs):
        """
        List review units matching the given query parameters.
        
        Returns:
            An iterable of review unit records matching the provided filters and pagination arguments.
        """
        return await self.reviews.list_units(*args, **kwargs)

    async def pending_count(self):
        """
        Get the number of review units that are currently pending.
        
        Returns:
            int: The count of pending reviews.
        """
        return await self.reviews.pending_count()

    async def pending_queue(self, *args, **kwargs):
        """
        Retrieve the pending review queue.
        
        Accepts positional and keyword arguments used to filter or page results; these are passed through to the underlying review implementation.
        
        Returns:
            A sequence of review records representing items that are pending review.
        """
        return await self.reviews.pending_queue(*args, **kwargs)

    async def recent_activity(self, *args, **kwargs):
        """
        Return recent review activity using the repository's query parameters.
        
        Returns:
            sequence: A sequence of review activity records matching the provided arguments and filters.
        """
        return await self.reviews.recent_activity(*args, **kwargs)

    async def set_review_status(self, unit_id: str, status: str, reviewed_by: str) -> None:
        """
        Set the review status for a knowledge unit and record the reviewer.
        
        Parameters:
            unit_id (str): Identifier of the knowledge unit to update.
            status (str): New review status to assign.
            reviewed_by (str): Identifier of the user who performed the review.
        """
        await self.reviews.set_status(unit_id, status, reviewed_by)

    # --- Users ---

    async def create_user(self, username: str, password_hash: str) -> None:
        """
        Create a new user with the given username and password hash.
        
        Parameters:
        	username (str): The desired unique username for the new user.
        	password_hash (str): The already-hashed password to store for the user.
        """
        await self.users.create(username, password_hash)

    async def get_user(self, username: str):
        """
        Return the user record matching the given username.
        
        Parameters:
            username (str): Username to look up.
        
        Returns:
            The user object if found, `None` otherwise.
        """
        return await self.users.get(username)

    # --- API keys ---

    async def count_active_api_keys_for_user(self, user_id: int) -> int:
        """
        Return the number of active API keys belonging to the specified user.
        
        Parameters:
            user_id (int): The numeric ID of the user.
        
        Returns:
            int: The count of active API keys for the given user.
        """
        return await self.api_keys.count_active_for_user(user_id)

    async def create_api_key(self, *args, **kwargs):
        """
        Create a new API key record.
        
        Returns:
            The created API key object.
        """
        return await self.api_keys.create(*args, **kwargs)

    async def get_active_api_key_by_id(self, key_id: str):
        """
        Retrieve the active API key with the specified identifier.
        
        Parameters:
            key_id (str): The API key identifier to look up.
        
        Returns:
            `APIKey` instance if an active key with the given identifier exists, `None` otherwise.
        """
        return await self.api_keys.get_active_by_id(key_id)

    async def get_api_key_for_user(self, *args, **kwargs):
        """
        Retrieve the active API key for a specific user.
        
        Returns:
            The active API key object for the user, or `None` if no active key exists.
        """
        return await self.api_keys.get_for_user(*args, **kwargs)

    async def list_api_keys_for_user(self, user_id: int):
        """
        List API keys belonging to the specified user.
        
        Parameters:
            user_id (int): ID of the user whose API keys to list.
        
        Returns:
            A list of API key records for the user.
        """
        return await self.api_keys.list_for_user(user_id)

    async def revoke_api_key(self, *args, **kwargs):
        """
        Revoke an API key.
        
        Parameters:
            *args: Positional arguments forwarded to the repository revoke method.
            **kwargs: Keyword arguments forwarded to the repository revoke method.
        
        Returns:
            The value returned by the repository revoke operation.
        """
        return await self.api_keys.revoke(*args, **kwargs)

    async def touch_api_key_last_used(self, key_id: str) -> None:
        """
        Update the last-used timestamp for the API key with the given identifier.
        
        Parameters:
            key_id (str): The API key identifier whose last-used timestamp should be updated.
        """
        await self.api_keys.touch_last_used(key_id)


def sqlite_url(db: Path) -> str:
    """
    Format a filesystem path as a SQLite URL using the `sqlite:///` scheme.
    
    Parameters:
        db (Path): Filesystem path to the SQLite database file.
    
    Returns:
        str: SQLite connection URL for the given path (e.g. `sqlite:////absolute/path`).
    """
    return f"sqlite:///{db}"


def init_test_db(db: Path) -> None:
    """
    Initialize a SQLite database file at the given path by running the production Alembic migrations.
    
    Parameters:
        db (Path): Filesystem path to the SQLite database file to create or migrate.
    """
    run_migrations(sqlite_url(db))


def _make_store(db_path: Path) -> _RepoBundle:
    """
    Build a fresh _RepoBundle configured for a single test SQLite file.
    
    Parameters:
        db_path (Path): Filesystem path for the SQLite database file; used to construct the database URL and stored in settings.
    
    Returns:
        _RepoBundle: A test repository bundle whose repositories share a Database configured to use the provided SQLite file.
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
