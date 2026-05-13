"""Exceptions raised by review services."""

from __future__ import annotations

from .base import ConflictError


class KnowledgeUnitAlreadyReviewedError(ConflictError):
    """Signal that a review decision was already recorded for a unit."""

    def __init__(self, status: str) -> None:
        """Create a conflict error with the existing review status."""
        super().__init__(f"Knowledge unit already {status}")
