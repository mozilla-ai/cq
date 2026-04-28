"""Resolve the database connection URL from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.engine import make_url

_DEFAULT_SQLITE_PATH = "/data/cq.db"


def resolve_database_url() -> str:
    """Return the SQLAlchemy URL for the cq server database.

    Precedence:
      1. ``CQ_DATABASE_URL`` if set — returned verbatim.
      2. ``CQ_DB_PATH`` — wrapped as ``sqlite:///<path>``.
      3. Default — ``sqlite:///`` + ``_DEFAULT_SQLITE_PATH``.
    """
    url = os.environ.get("CQ_DATABASE_URL")
    if url:
        return url
    path = os.environ.get("CQ_DB_PATH", _DEFAULT_SQLITE_PATH)
    return f"sqlite:///{path}"


def resolve_sqlite_db_path() -> tuple[str, Path]:
    """Return ``(url, path)`` for the cq SQLite database.

    Used by the FastAPI lifespan to drive both the migration runner and
    the ``SqliteStore`` from the same source — without this, setting
    ``CQ_DATABASE_URL`` would migrate one database while the runtime
    store opened another. Until the Postgres store lands (#309/#311)
    the runtime is SQLite-only, so a non-SQLite URL is rejected here
    rather than silently misconfiguring the server.
    """
    url = resolve_database_url()
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite"):
        raise RuntimeError(
            f"CQ_DATABASE_URL must be a SQLite URL until the Postgres store "
            f"lands (#309/#311); got driver {parsed.drivername!r}."
        )
    if not parsed.database or parsed.database == ":memory:":
        raise RuntimeError(
            "CQ_DATABASE_URL must point at a SQLite file; in-memory and blank databases are not supported."
        )
    return url, Path(parsed.database)
