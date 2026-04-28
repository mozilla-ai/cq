"""SqliteStore: SQLite-backed implementation of the async Store protocol.

Async surface implemented as a threadpool shim over a sync SQLAlchemy Core
engine. SQLite-native concerns (PRAGMAs, single-writer behaviour) live here;
portable SQL is sourced from ``cq_server.store._queries``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from cq.models import KnowledgeUnit
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

DEFAULT_DB_PATH = Path("/data/cq.db")


class SqliteStore:
    """SQLite-backed Store implementation. See module docstring."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._closed = False
        self._engine: Engine = create_engine(
            f"sqlite:///{self._db_path}",
            connect_args={"check_same_thread": False},
            future=True,
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await asyncio.to_thread(self._engine.dispose)

    async def insert(self, unit: KnowledgeUnit) -> None:
        raise NotImplementedError

    async def get(self, unit_id: str) -> KnowledgeUnit | None:
        raise NotImplementedError

    async def get_any(self, unit_id: str) -> KnowledgeUnit | None:
        raise NotImplementedError

    async def get_review_status(self, unit_id: str) -> dict[str, str | None] | None:
        raise NotImplementedError

    async def set_review_status(self, unit_id: str, status: str, reviewed_by: str) -> None:
        raise NotImplementedError

    async def update(self, unit: KnowledgeUnit) -> None:
        raise NotImplementedError

    async def query(
        self,
        domains: list[str],
        *,
        languages: list[str] | None = None,
        frameworks: list[str] | None = None,
        pattern: str = "",
        limit: int = 5,
    ) -> list[KnowledgeUnit]:
        raise NotImplementedError

    async def count(self) -> int:
        raise NotImplementedError

    async def domain_counts(self) -> dict[str, int]:
        raise NotImplementedError

    async def pending_queue(self, *, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def pending_count(self) -> int:
        raise NotImplementedError

    async def counts_by_status(self) -> dict[str, int]:
        raise NotImplementedError

    async def counts_by_tier(self) -> dict[str, int]:
        raise NotImplementedError

    async def list_units(
        self,
        *,
        domain: str | None = None,
        confidence_min: float | None = None,
        confidence_max: float | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def create_user(self, username: str, password_hash: str) -> None:
        raise NotImplementedError

    async def get_user(self, username: str) -> dict[str, Any] | None:
        raise NotImplementedError

    async def count_active_api_keys_for_user(self, user_id: int) -> int:
        raise NotImplementedError

    async def create_api_key(
        self,
        *,
        key_id: str,
        user_id: int,
        name: str,
        labels: list[str],
        key_prefix: str,
        key_hash: str,
        ttl: str,
        expires_at: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def get_api_key_for_user(self, *, user_id: int, key_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    async def get_active_api_key_by_id(self, key_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    async def list_api_keys_for_user(self, user_id: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def revoke_api_key(self, *, user_id: int, key_id: str) -> bool:
        raise NotImplementedError

    async def touch_api_key_last_used(self, key_id: str) -> None:
        raise NotImplementedError

    async def confidence_distribution(self) -> dict[str, int]:
        raise NotImplementedError

    async def recent_activity(self, limit: int = 20) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def daily_counts(self, *, days: int = 30) -> list[dict[str, Any]]:
        raise NotImplementedError
