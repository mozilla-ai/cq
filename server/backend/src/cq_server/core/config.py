"""Application configuration loaded from environment variables.

All ``CQ_*`` environment variables the server reads are consolidated here.
Settings are loaded eagerly at startup; downstream code asks for the
``Settings`` instance via the FastAPI dependency in ``api/deps.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_SQLITE_PATH = "/data/cq.db"


def database_url_from_env() -> str:
    """Resolve the database URL from env vars without instantiating ``Settings``.

    Used by the migration runner and the Alembic ``env.py``; both need the
    URL but neither needs the JWT secret or API-key pepper, so they
    shouldn't have to satisfy the rest of ``Settings``' required fields.
    Precedence matches ``Settings.resolved_database_url``: ``CQ_DATABASE_URL``
    > ``CQ_DB_PATH`` > built-in default.
    """
    url = os.environ.get("CQ_DATABASE_URL")
    if url:
        return url
    path = os.environ.get("CQ_DB_PATH", _DEFAULT_SQLITE_PATH)
    return f"sqlite:///{path}"


class Settings(BaseSettings):
    """Server configuration sourced from ``CQ_*`` environment variables."""

    model_config = SettingsConfigDict(env_prefix="CQ_", extra="ignore")

    # Required secrets — startup fails fast if either is missing.
    jwt_secret: str = Field(min_length=1)
    api_key_pepper: str = Field(min_length=1)

    # Database: ``database_url`` wins when set; otherwise ``db_path``
    # is wrapped as a ``sqlite:///`` URL. The default targets the
    # container path baked into the published image.
    database_url: str | None = None
    db_path: Path = Path(_DEFAULT_SQLITE_PATH)

    # HTTP listener.
    port: int = 3000

    @computed_field
    @property
    def resolved_database_url(self) -> str:
        """Return the SQLAlchemy URL, applying the db_path fallback.

        Precedence: ``CQ_DATABASE_URL`` > ``CQ_DB_PATH`` > built-in default.
        """
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.db_path}"
