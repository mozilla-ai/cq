"""Base exception hierarchy for service-layer errors."""

from __future__ import annotations


class ServiceError(Exception):
    """Signal that a service-layer operation failed."""

    def __init__(self, message: str) -> None:
        """Create a service error with a user-safe message."""
        super().__init__(message)
        self.message = message


class UnauthorizedError(ServiceError):
    """Signal that credentials are missing, invalid, or not permitted."""


class NotFoundError(ServiceError):
    """Signal that a requested resource does not exist."""


class ConflictError(ServiceError):
    """Signal that a request conflicts with current resource state."""


class ValidationError(ServiceError):
    """Signal that request data is semantically invalid."""
