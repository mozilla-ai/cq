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
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import ArgumentError

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
        """Build the engine from ``settings`` and register dialect hooks.

        SQLite URLs get a live engine with cq's required PRAGMAs.
        The canonical ``postgresql+psycopg://`` URL raises
        ``NotImplementedError`` until the Phase 2 implementation lands
        (#312). Other PostgreSQL driver suffixes are rejected with a
        message naming the canonical driver. Anything else raises
        ``ValueError``.
        """
        url = settings.resolved_database_url
        try:
            parsed = make_url(url)
        except ArgumentError as exc:
            raise ValueError("Invalid CQ_DATABASE_URL (could not parse as a database URL)") from exc
        driver = parsed.drivername
        if driver.startswith("sqlite"):
            sqlite_path = Path(url.removeprefix("sqlite:///"))
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            self._engine: Engine = create_engine(
                url,
                connect_args={"check_same_thread": False},
                future=True,
            )
            event.listen(self._engine, "connect", _apply_sqlite_pragmas)
        elif driver == "postgresql+psycopg":
            raise NotImplementedError(
                "PostgreSQL backend is not implemented yet; the psycopg "
                "v3-backed implementation lands in epic #257 (issue #312)."
            )
        elif driver == "postgresql" or driver.startswith("postgresql+"):
            raise NotImplementedError(
                f"PostgreSQL driver {driver!r} is not supported; "
                "use postgresql+psycopg:// once the PostgreSQL backend "
                "implementation lands in epic #257 (issue #312)."
            )
        else:
            raise ValueError(f"Unsupported database URL scheme: {driver!r}")
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
