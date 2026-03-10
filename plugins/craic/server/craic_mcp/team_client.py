"""HTTP client for the CRAIC Team API.

Wraps all team API endpoints with graceful degradation: connection
errors, timeouts, malformed responses, and schema mismatches all
return None instead of raising, so the MCP server can fall back to
local-only mode.
"""

import logging

import httpx
from pydantic import ValidationError

from .knowledge_unit import FlagReason, KnowledgeUnit

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 5.0

# Covers transport errors, HTTP status errors, JSON decode failures,
# and Pydantic schema mismatches.
_GRACEFUL_ERRORS = (httpx.HTTPError, ValueError, ValidationError)


class TeamClient:
    """Synchronous HTTP client for the CRAIC Team API.

    All methods return None (or False for health) when the team API is
    unreachable or returns an unexpected response, allowing the caller
    to degrade gracefully.

    Supports the context manager protocol for resource-safe usage.
    """

    def __init__(self, base_url: str, timeout: float = _DEFAULT_TIMEOUT) -> None:
        """Initialise the client.

        Args:
            base_url: Team API base URL (e.g. ``http://localhost:8742``).
            timeout: Request timeout in seconds.
        """
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    def __enter__(self) -> "TeamClient":
        """Enter the context manager."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Exit the context manager and close the client."""
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def health(self) -> bool:
        """Check whether the team API is reachable.

        Returns:
            True if the health endpoint responds with 200, False otherwise.
        """
        try:
            resp = self._client.get("/health")
            return resp.status_code == 200
        except _GRACEFUL_ERRORS:
            return False

    def query(
        self,
        domains: list[str],
        *,
        language: str | None = None,
        framework: str | None = None,
        limit: int = 5,
    ) -> list[KnowledgeUnit] | None:
        """Query the team store for knowledge units.

        Args:
            domains: Domain tags to search for.
            language: Optional programming language filter.
            framework: Optional framework filter.
            limit: Maximum results to return.

        Returns:
            List of matching knowledge units, or None if the team API
            is unreachable.
        """
        params: dict[str, str | int | list[str]] = {
            "domain": domains,
            "limit": limit,
        }
        if language:
            params["language"] = language
        if framework:
            params["framework"] = framework
        try:
            resp = self._client.get("/query", params=params)
            resp.raise_for_status()
            return [KnowledgeUnit.model_validate(item) for item in resp.json()]
        except _GRACEFUL_ERRORS:
            logger.debug("Team API query failed", exc_info=True)
            return None

    def propose(self, unit: KnowledgeUnit) -> KnowledgeUnit | None:
        """Push a knowledge unit to the team store.

        Args:
            unit: The knowledge unit to propose.

        Returns:
            The team-stored unit (with team tier and ID), or None if
            the team API is unreachable.
        """
        body = {
            "domain": unit.domain,
            "insight": unit.insight.model_dump(mode="json"),
            "context": unit.context.model_dump(mode="json"),
            "created_by": unit.created_by,
        }
        try:
            resp = self._client.post("/propose", json=body)
            resp.raise_for_status()
            return KnowledgeUnit.model_validate(resp.json())
        except _GRACEFUL_ERRORS:
            logger.debug("Team API propose failed", exc_info=True)
            return None

    def confirm(self, unit_id: str) -> KnowledgeUnit | None:
        """Confirm a knowledge unit in the team store.

        Args:
            unit_id: Knowledge unit ID to confirm.

        Returns:
            The updated knowledge unit, or None if the team API is
            unreachable or the unit was not found.
        """
        try:
            resp = self._client.post(f"/confirm/{unit_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return KnowledgeUnit.model_validate(resp.json())
        except _GRACEFUL_ERRORS:
            logger.debug("Team API confirm failed", exc_info=True)
            return None

    def flag(self, unit_id: str, reason: FlagReason) -> KnowledgeUnit | None:
        """Flag a knowledge unit in the team store.

        Args:
            unit_id: Knowledge unit ID to flag.
            reason: Flag reason.

        Returns:
            The updated knowledge unit, or None if the team API is
            unreachable or the unit was not found.
        """
        try:
            resp = self._client.post(
                f"/flag/{unit_id}",
                json={"reason": reason.value},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return KnowledgeUnit.model_validate(resp.json())
        except _GRACEFUL_ERRORS:
            logger.debug("Team API flag failed", exc_info=True)
            return None
