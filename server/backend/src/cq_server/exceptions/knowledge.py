"""Exceptions raised by knowledge services."""

from __future__ import annotations

from .base import NotFoundError, ValidationError


class KnowledgeUnitNotFoundError(NotFoundError):
    """Signal that a knowledge unit does not exist."""

    def __init__(self) -> None:
        """Create a stable not-found error for missing knowledge units."""
        super().__init__("Knowledge unit not found")


class InvalidDomainError(ValidationError):
    """Signal that domain tags are missing or invalid."""

    def __init__(self) -> None:
        """Create a stable validation error for invalid domain input."""
        super().__init__("At least one non-empty domain is required")
