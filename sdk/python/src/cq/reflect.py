"""Reflector protocol for mining session context into knowledge candidates."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Candidate:
    """A knowledge unit candidate extracted from session context."""

    summary: str
    detail: str
    action: str
    domains: list[str] = field(default_factory=list)
    relevance: float = 0.0


@dataclass(frozen=True, slots=True)
class ReflectResult:
    """Result of a reflection pass over session context."""

    candidates: list[Candidate] = field(default_factory=list)
    message: str = ""


class Reflector(Protocol):
    """Interface for extracting knowledge candidates from session context."""

    def reflect(self, session_context: str) -> ReflectResult:
        """Extract knowledge candidates from session context."""
        ...


class DefaultReflector:
    """Stub reflector that acknowledges context without extracting candidates.

    The actual extraction is performed by the agent (via the cq skill),
    which analyzes its own session context and calls propose directly.
    """

    def reflect(self, session_context: str) -> ReflectResult:
        """Return a guidance message for the agent to act on."""
        if not session_context.strip():
            return ReflectResult(message="Empty session context provided.")
        return ReflectResult(
            message="Session context received. Identify candidate knowledge units and submit each via propose."
        )
