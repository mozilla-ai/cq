"""Resolve the database connection URL from environment variables."""

from __future__ import annotations

import os

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
