"""Store package: protocol + concrete backends."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import make_url

from ._normalize import normalize_domains
from ._protocol import Store
from ._sqlite import DEFAULT_DB_PATH, SqliteStore

__all__ = [
    "DEFAULT_DB_PATH",
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

    SQLite URLs return a live ``SqliteStore``. Postgres URLs raise
    ``NotImplementedError`` until the Phase 2 ``PostgresStore`` lands
    (#311/#312); the message names those issues so the failure is
    self-explanatory. Anything else raises ``ValueError`` with the
    offending driver string.
    """
    parsed = make_url(database_url)
    driver = parsed.drivername
    if driver.startswith("sqlite"):
        if not parsed.database:
            raise ValueError(
                "SQLite URL must point at a file path; got an empty database."
            )
        if parsed.database == ":memory:":
            raise ValueError(
                "in-memory SQLite databases are not supported; the cq server "
                "needs a persistent file path."
            )
        return SqliteStore(db_path=Path(parsed.database))
    # Match every Postgres driver suffix (``+psycopg``, ``+psycopg2``,
    # ``+asyncpg``, …) so a typo'd driver still hits the helpful
    # NotImplementedError instead of falling through to the generic
    # "unsupported scheme" branch. Phase 2 (#311) will pick the actual
    # driver; until then anything postgres-shaped is rejected the same
    # way.
    if driver == "postgresql" or driver.startswith("postgresql+"):
        raise NotImplementedError(
            "PostgreSQL backend is not implemented yet; lands with "
            "PostgresStore in epic #257 (issues #311/#312)."
        )
    raise ValueError(f"Unsupported database URL scheme: {driver!r}")
