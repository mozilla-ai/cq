"""Async `Store` protocol for the cq server.

Pure interface definition — no implementations live here. Concrete
backends (`SqliteStore`, later `PostgresStore`) will conform to this
protocol so callers can depend on the surface without caring about
dialect. Early implementations may shim native sync drivers via a
threadpool; the protocol itself stays async.
"""

from typing import Any, Protocol, runtime_checkable

from cq.models import KnowledgeUnit


@runtime_checkable
class Store(Protocol):
    """Async storage protocol for the cq server.

    Implementations are expected to be one-per-dialect (`SqliteStore`,
    `PostgresStore`).
    """

    async def close(self) -> None:
        """Release underlying connections/resources; idempotent."""
        ...

    async def insert(self, unit: KnowledgeUnit) -> None:
        """Insert a knowledge unit; raises on id conflict or empty domains."""
        ...

    async def get(self, unit_id: str) -> KnowledgeUnit | None:
        """Return an approved KU by id, or None if missing or not approved."""
        ...

    async def get_any(self, unit_id: str) -> KnowledgeUnit | None:
        """Return a KU by id regardless of review status, or None if missing."""
        ...

    async def get_review_status(self, unit_id: str) -> dict[str, str | None] | None:
        """Return review metadata (status, reviewed_by, reviewed_at) or None."""
        ...

    async def set_review_status(self, unit_id: str, status: str, reviewed_by: str) -> None:
        """Update a KU's review status; raises KeyError if the id is unknown."""
        ...

    async def update(self, unit: KnowledgeUnit) -> None:
        """Replace an existing KU; raises KeyError if the id is unknown."""
        ...

    async def query(
        self,
        domains: list[str],
        *,
        languages: list[str] | None = None,
        frameworks: list[str] | None = None,
        pattern: str = "",
        limit: int = 5,
    ) -> list[KnowledgeUnit]:
        """Return approved KUs matching any of the domains, ranked by relevance."""
        ...

    async def count(self) -> int:
        """Return the total number of KUs in the store."""
        ...

    async def domain_counts(self) -> dict[str, int]:
        """Return approved KU counts keyed by domain tag."""
        ...

    async def pending_queue(self, *, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        """Return pending KUs with review metadata, oldest first."""
        ...

    async def pending_count(self) -> int:
        """Return the number of pending KUs."""
        ...

    async def counts_by_status(self) -> dict[str, int]:
        """Return KU counts keyed by review status."""
        ...

    async def counts_by_tier(self) -> dict[str, int]:
        """Return approved KU counts keyed by tier."""
        ...

    async def list_units(
        self,
        *,
        domain: str | None = None,
        confidence_min: float | None = None,
        confidence_max: float | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return KUs with review metadata, filtered by domain/confidence/status."""
        ...

    async def create_user(self, username: str, password_hash: str) -> None:
        """Insert a new user; raises on duplicate username."""
        ...

    async def get_user(self, username: str) -> dict[str, Any] | None:
        """Return user row by username, or None if missing."""
        ...

    async def count_active_api_keys_for_user(self, user_id: int) -> int:
        """Return the number of non-revoked, non-expired API keys for a user."""
        ...

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
        """Insert a new API key row and return the inserted row."""
        ...

    async def get_api_key_for_user(self, *, user_id: int, key_id: str) -> dict[str, Any] | None:
        """Return the key row if it exists and belongs to the user, else None."""
        ...

    async def get_active_api_key_by_id(self, key_id: str) -> dict[str, Any] | None:
        """Return the active key row (including the owner's username) by id, or None if missing, revoked, or expired."""
        ...

    async def list_api_keys_for_user(self, user_id: int) -> list[dict[str, Any]]:
        """Return all API keys owned by the user, newest first."""
        ...

    async def revoke_api_key(self, *, user_id: int, key_id: str) -> bool:
        """Mark the key revoked; return True if a row was updated."""
        ...

    async def touch_api_key_last_used(self, key_id: str) -> None:
        """Best-effort update of ``last_used_at``; errors are swallowed."""
        ...

    async def confidence_distribution(self) -> dict[str, int]:
        """Return confidence-bucket counts for approved KUs."""
        ...

    async def recent_activity(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent activity events (one per KU), newest first."""
        ...

    async def daily_counts(self, *, days: int = 30) -> list[dict[str, Any]]:
        """Return per-day proposed/approved/rejected counts; raises on days <= 0."""
        ...
