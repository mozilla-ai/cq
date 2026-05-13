"""Exceptions raised by API key services."""

from __future__ import annotations

from .base import ConflictError, NotFoundError, UnauthorizedError, ValidationError


class APIKeyInvalidError(UnauthorizedError):
    """Signal that an API key token is invalid."""

    def __init__(self) -> None:
        """Create a stable invalid-API-key service error."""
        super().__init__("Invalid API key")


class APIKeyTTLInvalidError(ValidationError):
    """Signal that an API key TTL value is invalid."""

    def __init__(self, message: str) -> None:
        """Create a TTL validation error with parser detail."""
        super().__init__(message)


class APIKeyActiveLimitReachedError(ConflictError):
    """Signal that a user has reached the active API key limit."""

    def __init__(self, limit: int) -> None:
        """Create a limit-reached error with the configured max."""
        super().__init__(f"Maximum of {limit} active API keys per user")


class APIKeyNotFoundError(NotFoundError):
    """Signal that an API key does not exist for the caller."""

    def __init__(self) -> None:
        """Create a stable not-found error for missing API keys."""
        super().__init__("API key not found")
