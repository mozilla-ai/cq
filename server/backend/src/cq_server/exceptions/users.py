"""Exceptions raised by user-related services."""

from __future__ import annotations

from .base import NotFoundError


class UserNotFoundError(NotFoundError):
    """Signal that a referenced user does not exist."""

    def __init__(self) -> None:
        """Create a stable not-found error for missing users."""
        super().__init__("User not found")
