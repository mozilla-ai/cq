"""Store package: protocol + concrete backends."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from ._normalize import normalize_domains
from ._postgres import PostgresStore
from ._protocol import Store
from ._sqlite import DEFAULT_DB_PATH, SqliteStore

__all__ = [
    "DEFAULT_DB_PATH",
    "PostgresStore",
    "SqliteStore",
    "Store",
    "create_store",
    "normalize_domains",
]


def create_store(database_url: str) -> Store:
    """Return the concrete ``Store`` for ``database_url``.

    Single dispatch point for URL → backend selection so the FastAPI
    lifespan and any future Postgres caller can't drift on which scheme
    maps to which store.

    SQLite URLs return a live ``SqliteStore``. The canonical
    ``postgresql+psycopg://...`` URL is dispatched through the
    ``PostgresStore`` stub, which raises ``NotImplementedError`` until
    the Phase 2 implementation lands (#312). Other PostgreSQL driver
    suffixes are rejected inline with a message naming the canonical
    driver. Anything else raises ``ValueError``.
    """
    try:
        parsed = make_url(database_url)
    except ArgumentError as exc:
        raise ValueError(f"Invalid CQ_DATABASE_URL: {database_url!r}") from exc
    driver = parsed.drivername
    if driver.startswith("sqlite"):
        if not parsed.database:
            raise ValueError("SQLite URL must point at a file path; got an empty database.")
        if parsed.database == ":memory:":
            raise ValueError(
                "in-memory SQLite databases are not supported; the cq server needs a persistent file path."
            )
        return SqliteStore(db_path=Path(parsed.database))
    if driver == "postgresql+psycopg":
        return PostgresStore(database_url)
    if driver == "postgresql" or driver.startswith("postgresql+"):
        raise NotImplementedError(
            f"PostgreSQL driver {driver!r} is not supported; use "
            "``postgresql+psycopg://...`` once the PostgresStore "
            "implementation lands in epic #257 (issue #312)."
        )
    raise ValueError(f"Unsupported database URL scheme: {driver!r}")
