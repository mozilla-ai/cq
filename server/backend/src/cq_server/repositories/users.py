"""User repository: account lookup and creation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from ..core.db import Database
from ._queries import INSERT_USER, SELECT_USER_BY_USERNAME


class UserRepository:
    """Read/write access to user accounts."""

    def __init__(self, db: Database) -> None:
        """Wire the repository to the shared ``Database``."""
        self._db = db

    async def create(self, username: str, password_hash: str) -> None:
        """Insert a new user. Surfaces the underlying integrity error on conflict."""
        await self._db.run_sync(self._create_sync, username, password_hash)

    async def get(self, username: str) -> dict[str, Any] | None:
        """Return the user row keyed by username, or ``None``."""
        return await self._db.run_sync(self._get_sync, username)

    def _create_sync(self, username: str, password_hash: str) -> None:
        created_at = datetime.now(UTC).isoformat()
        try:
            with self._db.engine.begin() as conn:
                conn.execute(
                    INSERT_USER,
                    {"username": username, "password_hash": password_hash, "created_at": created_at},
                )
        except IntegrityError as e:
            if e.orig is not None:
                raise e.orig from e
            raise

    def _get_sync(self, username: str) -> dict[str, Any] | None:
        with self._db.engine.connect() as conn:
            row = conn.execute(SELECT_USER_BY_USERNAME, {"username": username}).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "created_at": row[3],
        }
