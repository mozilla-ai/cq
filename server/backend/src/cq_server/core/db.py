"""Shared database engine + threadpool shim used by every repository.

Repositories own SQL; this module owns the SQLAlchemy engine, SQLite-specific
PRAGMAs, and the ``run_sync`` adapter that lets sync ``Engine`` calls coexist
with FastAPI's async event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from .config import Settings


def _apply_sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # noqa: ANN001 (sqlalchemy event signature)
    """Issue cq's required SQLite PRAGMAs on every new connection.

    Invoked by SQLAlchemy's ``connect`` event so the pool's per-thread
    connections all receive the same pragmas. ``executescript`` is avoided to
    keep each pragma in its own statement (SQLite docs: some pragmas only
    take effect outside a transaction).
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.execute("PRAGMA busy_timeout = 5000")
    finally:
        cursor.close()


class Database:
    """SQLAlchemy engine wrapper with a sync→async shim for repositories.

    The engine is owned here so that repositories don't each create their
    own connection pool; the shim funnels every blocking call through
    ``asyncio.to_thread`` and centralises the post-close guard.
    """

    def __init__(self, settings: Settings) -> None:
        """Build the engine from ``settings`` and register the SQLite PRAGMA hook."""
        url = settings.resolved_database_url
        if url.startswith("sqlite:///"):
            # Derive the file path from the resolved URL itself rather than
            # ``settings.db_path``, because ``CQ_DATABASE_URL`` (when set)
            # wins over ``CQ_DB_PATH`` and the two can disagree.
            sqlite_path = Path(url.removeprefix("sqlite:///"))
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            self._engine: Engine = create_engine(
                url,
                connect_args={"check_same_thread": False},
                future=True,
            )
            event.listen(self._engine, "connect", _apply_sqlite_pragmas)
        else:
            # PostgreSQL backend is gated by #311/#312; lifespan resolves
            # the URL up-front so this branch should be unreachable in
            # normal flows. Surface a clear error if anything ever reaches
            # here so the failure mode isn't a cryptic driver error.
            raise NotImplementedError(
                f"Only sqlite:// URLs are supported (got {url!r}). See #311/#312.",
            )
        self._closed = False

    @property
    def engine(self) -> Engine:
        """Return the underlying SQLAlchemy engine.

        Repositories use this to open ``connect()`` / ``begin()`` blocks
        inside their ``_*_sync`` methods.
        """
        return self._engine

    async def close(self) -> None:
        """Dispose of the underlying engine. Idempotent."""
        if self._closed:
            return
        self._closed = True
        await asyncio.to_thread(self._engine.dispose)

    async def run_sync(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        """Run a sync callable on the default executor and await its result.

        Every repository public async method funnels SQL work through this
        shim so the sqlite3 driver's blocking calls don't tie up the event
        loop. The closed-state guard lives here so callers don't have to
        repeat it.

        Raises:
            RuntimeError: If the database has already been closed.
        """
        if self._closed:
            raise RuntimeError("Database is closed")
        return await asyncio.to_thread(fn, *args, **kwargs)
