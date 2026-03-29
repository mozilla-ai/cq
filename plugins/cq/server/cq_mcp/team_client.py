"""HTTP client for the cq Team API.

Wraps all team API endpoints with graceful degradation: connection
errors, timeouts, malformed responses, and schema mismatches return
structured error context (for query) or None (for other methods)
instead of raising, so the MCP server can fall back to local-only mode.
"""

import dataclasses
import logging

import httpx
from pydantic import ValidationError

from .knowledge_unit import FlagReason, KnowledgeUnit

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 5.0

# Covers transport errors, HTTP status errors, JSON decode failures,
# and Pydantic schema mismatches.
_GRACEFUL_ERRORS = (httpx.HTTPError, ValueError, ValidationError)


@dataclasses.dataclass(frozen=True, slots=True)
class TeamQueryResult:
    """Result of a team API query, carrying both data and error context."""

    units: list[KnowledgeUnit] | None
    error: str | None = None


class TeamRejectedError(Exception):
    """Raised when the team API explicitly rejects a request (HTTP 4xx/5xx)."""

    def __init__(self, status_code: int, detail: str) -> None:
        """Initialise with the HTTP status code and response body."""
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Team API rejected request ({status_code}): {detail}")


class TeamClient:
    """Async HTTP client for the cq Team API.

    Most methods return None (or False for health) when the team API is
    unreachable or returns an unexpected response, allowing the caller
    to degrade gracefully. ``query()`` returns a ``TeamQueryResult``
    with error context instead of None, so callers can surface the
    failure reason.

    Supports the async context manager protocol for resource-safe usage.
    """

    def __init__(self, base_url: str, timeout: float = _DEFAULT_TIMEOUT) -> None:
        """Initialise the client.

        Args:
            base_url: Team API base URL (e.g. ``http://localhost:8742``).
            timeout: Request timeout in seconds.
        """
        self._base_url = base_url
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    @property
    def base_url(self) -> str:
        """Return the configured team API base URL."""
        return self._base_url

    async def __aenter__(self) -> "TeamClient":
        """Enter the async context manager."""
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Exit the async context manager and close the client."""
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def health(self) -> bool:
        """Check whether the team API is reachable.

        Returns:
            True if the health endpoint responds with 200, False otherwise.
        """
        try:
            resp = await self._client.get("/health")
            return resp.status_code == 200
        except _GRACEFUL_ERRORS:
            return False

    async def query(
        self,
        domains: list[str],
        *,
        language: str | None = None,
        framework: str | None = None,
        limit: int = 5,
    ) -> TeamQueryResult:
        """Query the team store for knowledge units.

        Args:
            domains: Domain tags to search for.
            language: Optional programming language filter.
            framework: Optional framework filter.
            limit: Maximum results to return.

        Returns:
            A TeamQueryResult with matching units, or with units=None
            and an error message if the team API is unreachable.
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
            resp = await self._client.get("/query", params=params)
            resp.raise_for_status()
            units = [KnowledgeUnit.model_validate(item) for item in resp.json()]
            return TeamQueryResult(units=units)
        except _GRACEFUL_ERRORS as exc:
            logger.warning("Team API query failed", exc_info=True)
            return TeamQueryResult(units=None, error=str(exc))

    async def propose(self, unit: KnowledgeUnit) -> KnowledgeUnit | None:
        """Push a knowledge unit to the team store.

        Args:
            unit: The knowledge unit to propose.

        Returns:
            The team-stored unit (with team tier and ID), or None if
            the team API is unreachable due to a transport error.

        Raises:
            TeamRejectedError: If the team API explicitly rejects the
                proposal with an HTTP 4xx/5xx status.
        """
        body = {
            "id": unit.id,
            "domain": unit.domain,
            "insight": unit.insight.model_dump(mode="json"),
            "context": unit.context.model_dump(mode="json"),
            "evidence": unit.evidence.model_dump(mode="json"),
            "created_by": unit.created_by,
        }
        try:
            resp = await self._client.post("/propose", json=body)
            resp.raise_for_status()
            return KnowledgeUnit.model_validate(resp.json())
        except httpx.HTTPStatusError as exc:
            raise TeamRejectedError(
                status_code=exc.response.status_code,
                detail=exc.response.text,
            ) from exc
        except _GRACEFUL_ERRORS:
            logger.debug("Team API propose unreachable", exc_info=True)
            return None

    async def confirm(self, unit_id: str) -> KnowledgeUnit | None:
        """Confirm a knowledge unit in the team store.

        Args:
            unit_id: Knowledge unit ID to confirm.

        Returns:
            The updated knowledge unit, or None if the team API is
            unreachable or the unit was not found.
        """
        try:
            resp = await self._client.post(f"/confirm/{unit_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return KnowledgeUnit.model_validate(resp.json())
        except _GRACEFUL_ERRORS:
            logger.debug("Team API confirm failed", exc_info=True)
            return None

    async def flag(self, unit_id: str, reason: FlagReason) -> KnowledgeUnit | None:
        """Flag a knowledge unit in the team store.

        Args:
            unit_id: Knowledge unit ID to flag.
            reason: Flag reason.

        Returns:
            The updated knowledge unit, or None if the team API is
            unreachable or the unit was not found.
        """
        try:
            resp = await self._client.post(
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
