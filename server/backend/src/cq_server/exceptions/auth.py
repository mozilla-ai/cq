"""Exceptions raised by authentication services."""

from __future__ import annotations

from .base import UnauthorizedError


class InvalidCredentialsError(UnauthorizedError):
    """Signal that username/password credentials are invalid."""

    def __init__(self) -> None:
        """Create a stable invalid-credentials service error."""
        super().__init__("Invalid username or password")
