"""Shared database engine + threadpool shim used by every repository.

Repositories own SQL; this module owns the SQLAlchemy engine, SQLite-specific
PRAGMAs, and the ``run_sync`` adapter that lets sync ``Engine`` calls coexist
with FastAPI's async event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import ArgumentError

from ..semsearch import _ENABLED as _SEMSEARCH_ENABLED
from ..semsearch import load as semsearch_load
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

        SQLite URLs get a live engine with cq's required PRAGMAs. The
        canonical ``postgresql+psycopg://`` URL gets a UTC-pinned engine
        (and fails fast if semantic search is enabled, which has no PG
        backend yet). Other PostgreSQL
        driver suffixes are rejected with a message naming the canonical
        driver. Anything else raises ``ValueError``.
        """
        url = settings.resolved_database_url
        try:
            parsed = make_url(url)
        except ArgumentError as exc:
            raise ValueError("Invalid CQ_DATABASE_URL (could not parse as a database URL)") from exc
        driver = parsed.drivername
        if driver.startswith("sqlite"):
            database = parsed.database
            if database and database != ":memory:":
                Path(database).parent.mkdir(parents=True, exist_ok=True)
            self._engine: Engine = create_engine(
                url,
                connect_args={"check_same_thread": False},
                future=True,
            )
            event.listen(self._engine, "connect", _apply_sqlite_pragmas)
            if _SEMSEARCH_ENABLED:
                event.listen(self._engine, "connect", semsearch_load)
        elif driver == "postgresql+psycopg":
            if _SEMSEARCH_ENABLED:
                # semsearch runs sqlite-vec SQL; it has no PG implementation
                # yet. Fail fast rather than blow up on the first insert.
                raise RuntimeError(
                    "semantic search is not yet supported on the PostgreSQL backend; "
                    "unset TOKEN_EMBEDDING_URL to run cq against PostgreSQL."
                )
            self._engine = create_engine(
                url,
                # Force UTC so ``to_char(col::timestamptz, ...)`` renders in UTC,
                # matching SQLite's ``date()`` on ISO strings.
                connect_args={"options": "-c timezone=utc", "connect_timeout": 10},
                pool_pre_ping=True,
                future=True,
            )
        elif driver == "postgresql" or driver.startswith("postgresql+"):
            raise NotImplementedError(
                f"PostgreSQL driver {driver!r} is not supported; "
                "use the canonical postgresql+psycopg:// driver instead."
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

    async def run_clauses_in_transaction(self, clauses: list[tuple[Any, dict[str, Any]]]) -> None:
        """Execute a list of SQL clauses in a single transaction.

        Parameters:
            clauses: List of tuples containing (statement, parameters_dict) to execute.

        Raises:
            RuntimeError: If the database has already been closed.
        """
        return await self.run_sync(self.run_clauses_sync, clauses)

    def run_clauses_sync(
        self,
        clauses: list[tuple[Any, dict[str, Any]]],
        *,
        fetch: bool = False,
    ) -> Sequence[Any]:
        """Execute clauses in one transaction and optionally fetch the last result set.

        When ``fetch`` is ``True``, this returns ``fetchall()`` from the final
        executed statement if it produces rows, otherwise an empty list.
        """
        if not clauses:
            return []

        rows: Sequence[Any] = []
        with self._engine.begin() as conn:
            result = None
            for statement, params in clauses:
                result = conn.execute(statement, params)
            if fetch and result is not None and result.returns_rows:
                rows = result.fetchall()
        return rows
