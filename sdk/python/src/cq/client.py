"""Client — the public interface to the cq knowledge commons.

Handles remote mode (HTTP calls to a cq API) and local mode
(SQLite at $XDG_DATA_HOME/cq/local.db), with fallback between them.
"""

import contextlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from pydantic import ValidationError

from ._util import _as_list
from .discovery import Resolver, default_cache_dir
from .models import (
    Context,
    FlagReason,
    Insight,
    KnowledgeUnit,
    Tier,
    create_knowledge_unit,
)
from .scoring import apply_confirmation, apply_flag
from .store import LocalStore, StoreStats

_DEFAULT_TIMEOUT = 5.0

# Attach a NullHandler to the package-level "cq" logger so the SDK is silent
# unless the caller wires a handler.
# This is load-bearing for MCP-over-stdio transports where any stray write to
# stderr or stdout corrupts the JSONRPC stream.
# The NullHandler is installed on the parent "cq" logger so it covers every
# sub-logger in the SDK (cq.client, cq.discovery, cq.store, etc.).
logging.getLogger("cq").addHandler(logging.NullHandler())


@dataclass(frozen=True, slots=True)
class DrainResult:
    """Result of a drain operation."""

    # Number of local units successfully pushed to the remote API.
    pushed: int = 0

    # Non-fatal issues encountered during the drain. Each entry
    # describes a unit that could not be pushed, either because the
    # remote was unreachable or because it rejected the request.
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class QueryResult:
    """Result of a query operation."""

    # Whether the query consulted only the local store ("local") or
    # also reached a remote API ("remote"). This is metadata about the
    # query itself, not about individual units.
    source: str

    # Matched knowledge units, potentially merged from local and remote
    # stores. Each unit's tier field indicates its origin and determines
    # how subsequent operations (confirm, flag) are routed.
    units: list["KnowledgeUnit"] = field(default_factory=list)

    # Non-fatal issues encountered during the query, such as a remote
    # API being unreachable or returning an unparseable response.
    warnings: list[str] = field(default_factory=list)


class RemoteError(Exception):
    """Raised when the remote API explicitly rejects a request."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Remote API rejected request ({status_code}): {detail}")


class FallbackError(Exception):
    """Raised when propose stored a unit locally after a remote failure.

    The unit has been persisted to the local store and will drain to the
    remote on the next successful connection. The underlying cause is
    available via ``__cause__`` (set automatically by ``raise ... from``);
    this is a ``RemoteError`` for auth rejection (401/403) or a transport
    exception for connectivity issues.
    """

    def __init__(self, local_unit: "KnowledgeUnit") -> None:
        self.local_unit = local_unit
        super().__init__("Stored locally after remote failure")


class Client:
    """Client for the cq shared knowledge commons.

    Queries, proposes, confirms, and flags knowledge units against a
    remote cq API or a local SQLite store.

    When no remote address is configured, operates in local-only mode.
    When the remote API is unreachable, falls back to local storage.
    """

    def __init__(
        self,
        addr: str | None = None,
        local_db_path: Path | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        logger: logging.Logger | None = None,
        _resolver: Resolver | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            addr: Remote cq API address. Reads from CQ_ADDR
                env var if not provided. None = local-only mode.
            local_db_path: Local SQLite path. Reads from CQ_LOCAL_DB_PATH
                env var if not provided. Defaults to $XDG_DATA_HOME/cq/local.db.
            timeout: HTTP request timeout in seconds. Defaults to 5.0.
            logger: Logger for SDK diagnostics.
                Defaults to ``logging.getLogger("cq.client")``.
                The library installs a NullHandler on the parent ``cq`` logger at import time,
                so the SDK is silent unless the caller wires a handler.
            _resolver: Private test seam for injecting a pre-built Resolver.
                Not part of the public API; the leading underscore signals that
                callers outside the SDK's own tests should leave this unset.
        """
        self._addr = addr or os.environ.get("CQ_ADDR")
        db_path = local_db_path or _db_path_from_env()
        self._store = LocalStore(db_path=db_path)
        self._logger = logger if logger is not None else logging.getLogger("cq.client")
        self._http: httpx.Client | None = None
        self._resolver: Resolver | None = None
        if self._addr:
            api_key = os.environ.get("CQ_API_KEY", "")
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            self._http = httpx.Client(
                timeout=timeout,
                headers=headers,
            )
            self._resolver = (
                _resolver
                if _resolver is not None
                else Resolver(
                    cache_dir=default_cache_dir(),
                    http_client=self._http,
                    logger=self._logger,
                )
            )

    def close(self) -> None:
        """Close the local store, the Resolver, and the HTTP client."""
        self._store.close()
        if self._resolver is not None:
            self._resolver.close()
        if self._http is not None:
            self._http.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def addr(self) -> str | None:
        """The configured remote API address, or None for local-only mode."""
        return self._addr

    def query(
        self,
        domains: list[str],
        *,
        languages: list[str] | None = None,
        frameworks: list[str] | None = None,
        pattern: str = "",
        limit: int = 5,
    ) -> QueryResult:
        """Search for knowledge units by domain tags.

        Queries both the local store and remote API (if configured),
        merging and deduplicating results.

        Returns:
            A QueryResult with matched units, a source indicator
            (``"local"`` or ``"remote"``), and any warnings.
        """
        domains = _as_list(domains)
        if languages is not None:
            languages = _as_list(languages)
        if frameworks is not None:
            frameworks = _as_list(frameworks)

        source = "local"
        warnings: list[str] = []
        local_results = self._store.query(
            domains,
            languages=languages,
            frameworks=frameworks,
            pattern=pattern,
            limit=limit,
        )

        if self._http is None:
            return QueryResult(units=local_results, source=source)

        remote_results: list[KnowledgeUnit] = []
        try:
            remote_results = self._remote_query(
                domains,
                languages=languages,
                frameworks=frameworks,
                pattern=pattern,
                limit=limit,
            )
            source = "remote"
        except (httpx.HTTPError, ValueError, ValidationError, TypeError) as exc:
            warnings.append(f"Remote query failed: {exc}")

        merged = _merge_results(local_results, remote_results, limit)
        return QueryResult(units=merged, source=source, warnings=warnings)

    def propose(
        self,
        summary: str,
        detail: str,
        action: str,
        domains: list[str],
        *,
        languages: list[str] | None = None,
        frameworks: list[str] | None = None,
        pattern: str = "",
        created_by: str = "",
    ) -> KnowledgeUnit:
        """Propose a new knowledge unit.

        When a remote API is configured and reachable, the unit is sent to
        the remote only and returned with no exception. The remote is the
        source of truth for server-assigned fields; in particular, ``tier``
        is promoted to ``PRIVATE`` and ``created_by`` is overwritten with
        the authenticated caller. If the remote is unreachable
        (transport/5xx) or rejects the request with an auth error
        (401/403), the unit is stored locally with ``tier=LOCAL`` and
        ``FallbackError`` is raised carrying the local unit and the
        underlying cause; the unit will drain on the next successful
        connection. Other 4xx errors (400, 409, 422) raise ``RemoteError``
        with nothing stored — the data is the problem, not connectivity.
        With no remote configured, always stores locally with no
        exception.
        """
        domains = _as_list(domains)
        if languages is not None:
            languages = _as_list(languages)
        if frameworks is not None:
            frameworks = _as_list(frameworks)
        context = Context(
            languages=languages or [],
            frameworks=frameworks or [],
            pattern=pattern,
        )
        unit = create_knowledge_unit(
            domains=domains,
            insight=Insight(summary=summary, detail=detail, action=action),
            context=context,
            created_by=created_by,
        )
        remote_cause: Exception | None = None
        result: KnowledgeUnit | None = None

        if self._http is not None:
            try:
                result = self._remote_propose(unit)
            except RemoteError as exc:
                if exc.status_code not in (401, 403) and not (500 <= exc.status_code < 600):
                    raise
                remote_cause = exc
            except httpx.HTTPError as exc:
                remote_cause = exc
            if result is not None:
                return result

        try:
            self._store.insert(unit)
        except Exception as insert_exc:
            if remote_cause is not None:
                raise RuntimeError(f"fallback insert after remote failure: {insert_exc}") from remote_cause
            raise

        if remote_cause is not None:
            raise FallbackError(local_unit=unit) from remote_cause
        return unit

    def confirm(self, unit_id: str, *, tier: Tier = Tier.LOCAL) -> KnowledgeUnit:
        """Confirm a knowledge unit, boosting its confidence.

        Uses tier to determine where to route the confirmation:
        - LOCAL: operates on local store, forwards to remote if configured.
        - Non-local (PRIVATE, PUBLIC): routes directly to the remote API.

        Raises:
            KeyError: If the unit is not found in the local store (LOCAL tier)
                or if the remote is unreachable (non-local tiers).
            RemoteError: If the remote API explicitly rejects the request,
                including HTTP 404/410.
            RuntimeError: If a non-local tier is specified without a remote API.
        """
        if tier == Tier.LOCAL:
            unit = self._store.get(unit_id)
            if unit is None:
                raise KeyError(f"Knowledge unit not found: {unit_id}")
            confirmed = apply_confirmation(unit)
            self._store.update(confirmed)
            if self._http is not None:
                with contextlib.suppress(RemoteError):
                    self._remote_confirm(unit_id)
            return confirmed

        if self._http is None:
            raise RuntimeError("Cannot confirm non-local unit without remote API configured")
        result = self._remote_confirm(unit_id)
        if result is not None:
            return result
        raise KeyError(f"Remote unreachable; cannot confirm unit: {unit_id}")

    def flag(self, unit_id: str, reason: FlagReason, *, tier: Tier = Tier.LOCAL) -> KnowledgeUnit:
        """Flag a knowledge unit, reducing its confidence.

        Uses tier to determine where to route the flag:
        - LOCAL: operates on local store, forwards to remote if configured.
        - Non-local (PRIVATE, PUBLIC): routes directly to the remote API.

        Raises:
            KeyError: If the unit is not found in the local store (LOCAL tier)
                or if the remote is unreachable (non-local tiers).
            RemoteError: If the remote API explicitly rejects the request,
                including HTTP 404/410.
            RuntimeError: If a non-local tier is specified without a remote API.
        """
        if tier == Tier.LOCAL:
            unit = self._store.get(unit_id)
            if unit is None:
                raise KeyError(f"Knowledge unit not found: {unit_id}")
            flagged = apply_flag(unit, reason)
            self._store.update(flagged)
            if self._http is not None:
                with contextlib.suppress(RemoteError):
                    self._remote_flag(unit_id, reason)
            return flagged

        if self._http is None:
            raise RuntimeError("Cannot flag non-local unit without remote API configured")
        result = self._remote_flag(unit_id, reason)
        if result is not None:
            return result
        raise KeyError(f"Remote unreachable; cannot flag unit: {unit_id}")

    def _stats_section(self, remote: dict, key: str, stats: StoreStats) -> dict:
        """Return ``remote[key]`` when it is a mapping, else warn and return empty.

        A remote that omits a section is fine (treated as empty). One that sends
        a non-object section (e.g. ``null`` or a list) degrades to local-only
        counts for that section with a warning, rather than raising and losing
        the whole status.
        """
        value = remote.get(key, {})
        if isinstance(value, dict):
            return value
        message = f"Ignoring non-object {key!r} in remote stats"
        self._logger.warning(message)
        stats.warnings.append(message)
        return {}

    def status(self) -> StoreStats:
        """Return knowledge store statistics with tier counts.

        When a remote API is configured and reachable, tier counts include
        both local and remote breakdowns. If the remote stats request fails,
        only local counts are returned, the failure is logged at warn level,
        and a non-fatal entry is added to ``StoreStats.warnings`` so callers
        can distinguish an unreachable remote from a genuinely empty store.

        Remote tier keys are coerced to ``Tier``; a tier this SDK does not
        recognize is skipped, logged at warn level, and recorded in
        ``StoreStats.warnings``, so its count is dropped from the totals rather
        than carried as a bare string.

        ``confidence_distribution`` sums the local buckets with the remote's
        reported buckets (the caller's private/org units), so it covers
        everything except the public commons. Local and remote share the
        canonical bucket labels; a label this SDK does not recognize is
        skipped, logged, and recorded in ``StoreStats.warnings``.
        """
        stats = self._store.stats()
        stats.tier_counts = {Tier.LOCAL: stats.total_count}
        # The local store seeds every canonical bucket, so its keys are the
        # label set a remote distribution must match to merge.
        known_buckets = set(stats.confidence_distribution)

        if self._http is not None:
            try:
                remote = self._remote_stats()
            except (httpx.HTTPError, ValueError) as exc:
                # Surface the failure rather than silently reporting local-only
                # counts that look identical to a genuinely empty store. Log via
                # the SDK logger (NullHandler by default, so MCP-over-stdio stays
                # clean) and carry a warning to the caller.
                self._logger.warning("Remote stats unavailable: %s", exc)
                stats.warnings.append(f"Remote stats unavailable: {exc}")
            else:
                for tier_key, count in self._stats_section(remote, "tier_counts", stats).items():
                    try:
                        tier = Tier(tier_key)
                    except ValueError:
                        # A tier this SDK's enum does not know (e.g. a newer
                        # server). Skip it rather than carry a bare string. Log
                        # and surface a warning so the dropped count stays
                        # visible to callers even when the SDK logger is
                        # silenced by the default NullHandler.
                        message = f"Ignoring unknown tier {tier_key!r} in remote stats"
                        self._logger.warning(message)
                        stats.warnings.append(message)
                        continue
                    # The remote store should never report a "local" tier, but guard
                    # against it to prevent overwriting the local count we already set.
                    if tier == Tier.LOCAL:
                        continue
                    stats.tier_counts[tier] = count
                    stats.total_count += count
                for domain, count in self._stats_section(remote, "domain_counts", stats).items():
                    stats.domain_counts[domain] = stats.domain_counts.get(domain, 0) + count
                for label, count in self._stats_section(remote, "confidence_distribution", stats).items():
                    if label not in known_buckets:
                        # A bucket label this SDK does not recognize (e.g. a
                        # newer server). Skip it rather than carry an unknown
                        # key. Log and surface a warning so the dropped count
                        # stays visible even when the SDK logger is silenced by
                        # the default NullHandler.
                        message = f"Ignoring unknown confidence bucket {label!r} in remote stats"
                        self._logger.warning(message)
                        stats.warnings.append(message)
                        continue
                    stats.confidence_distribution[label] = stats.confidence_distribution.get(label, 0) + count

        return stats

    def drain(self) -> DrainResult:
        """Push all local-only units to the remote API.

        Returns:
            A DrainResult with the number of units pushed and any warnings.

        Raises:
            RuntimeError: If no remote API is configured.
        """
        if self._http is None:
            raise RuntimeError("No remote API configured")

        units = self._store.all()
        pushed = 0
        warnings: list[str] = []
        for unit in units:
            if unit.tier == Tier.LOCAL:
                try:
                    self._remote_propose(unit)
                    self._store.delete(unit.id)
                    pushed += 1
                except RemoteError as exc:
                    warnings.append(f"Failed to drain unit {unit.id}: {exc}")
                except httpx.HTTPError as exc:
                    warnings.append(f"Failed to drain unit {unit.id}: {exc}")
        return DrainResult(pushed=pushed, warnings=warnings)

    # -- Remote HTTP helpers (graceful degradation) --

    def _api_base_url(self) -> str:
        """Return the resolved API base URL for the configured node.

        Any trailing slash in the resolved value is stripped so each call
        site can append a leading-slash resource path (e.g. `/knowledge`)
        without producing `//` in the request URL.
        Memoization lives in the Resolver; this helper keeps each call site
        a single statement so request URLs read uniformly across `_remote_*`.
        """
        assert self._addr is not None and self._resolver is not None
        return self._resolver.resolve(self._addr).api_base_url.rstrip("/")

    def _remote_stats(self) -> dict:
        """Fetch store statistics from the remote API.

        Returns:
            The decoded stats dict on success.

        Raises:
            httpx.HTTPError: For transport-layer or HTTP status failures.
            ValueError: If the response body is not a JSON object (invalid
                JSON, or a valid non-object such as an array or string).
        """
        assert self._http is not None
        resp = self._http.get(f"{self._api_base_url()}/knowledge/stats")
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            raise ValueError("expected a JSON object from the knowledge stats endpoint")
        return body

    def _remote_query(
        self,
        domains: list[str],
        *,
        languages: list[str] | None = None,
        frameworks: list[str] | None = None,
        pattern: str = "",
        limit: int = 5,
    ) -> list[KnowledgeUnit]:
        """Query the remote API.

        Raises on failure so the caller can decide how to handle it.
        """
        assert self._http is not None
        params: dict[str, str | int | list[str]] = {
            "domains": domains,
            "limit": limit,
        }
        if languages:
            params["languages"] = languages
        if frameworks:
            params["frameworks"] = frameworks
        if pattern:
            params["pattern"] = pattern
        resp = self._http.get(f"{self._api_base_url()}/knowledge", params=params)
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict) or "data" not in body:
            raise ValueError("expected {data: [...]} envelope from knowledge list endpoint")
        return [KnowledgeUnit.model_validate(item) for item in body["data"]]

    def _remote_propose(self, unit: KnowledgeUnit) -> KnowledgeUnit:
        """Push a unit to the remote API.

        Returns:
            The server-created KnowledgeUnit on success.

        Raises:
            RemoteError: If the remote API explicitly rejects the request.
            httpx.HTTPError: For transport-layer failures (connect, timeout,
                read, network errors). Callers decide how to classify.
        """
        assert self._http is not None
        body = {
            "domains": unit.domains,
            "insight": unit.insight.model_dump(mode="json"),
            "context": unit.context.model_dump(mode="json"),
            "created_by": unit.created_by,
        }
        try:
            resp = self._http.post(f"{self._api_base_url()}/knowledge", json=body)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RemoteError(
                status_code=exc.response.status_code,
                detail=exc.response.text,
            ) from exc
        try:
            data = resp.json()
            unit_data = data.get("knowledge_unit", data) if isinstance(data, dict) else data
            return KnowledgeUnit.model_validate(unit_data)
        except (ValueError, ValidationError):
            # Server accepted (2xx) but response is not a parseable KU.
            # Return the unit with tier promoted and server-assigned fields
            # cleared; callers should not trust values that only the server
            # sets.
            cleared_evidence = unit.evidence.model_copy(update={"first_observed": None, "last_confirmed": None})
            return unit.model_copy(update={"tier": Tier.PRIVATE, "created_by": "", "evidence": cleared_evidence})

    def _remote_confirm(self, unit_id: str) -> KnowledgeUnit | None:
        """Confirm a unit on the remote API.

        Returns:
            The confirmed KnowledgeUnit on success, None on transport error.

        Raises:
            RemoteError: If the remote API explicitly rejects the request
                or returns an unparseable response.
        """
        assert self._http is not None
        try:
            resp = self._http.post(f"{self._api_base_url()}/knowledge/{unit_id}/confirmations")
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RemoteError(
                status_code=exc.response.status_code,
                detail=exc.response.text,
            ) from exc
        except httpx.HTTPError:
            return None
        try:
            data = resp.json()
            unit_data = data.get("knowledge_unit", data) if isinstance(data, dict) else data
            return KnowledgeUnit.model_validate(unit_data)
        except (ValueError, ValidationError) as exc:
            raise RemoteError(
                status_code=resp.status_code,
                detail=f"Invalid response body: {exc}",
            ) from exc

    def _remote_flag(self, unit_id: str, reason: FlagReason) -> KnowledgeUnit | None:
        """Flag a unit on the remote API.

        Returns:
            The flagged KnowledgeUnit on success, None on transport error.

        Raises:
            RemoteError: If the remote API explicitly rejects the request
                or returns an unparseable response.
        """
        assert self._http is not None
        try:
            resp = self._http.post(
                f"{self._api_base_url()}/knowledge/{unit_id}/flags",
                json={"reason": reason.value},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RemoteError(
                status_code=exc.response.status_code,
                detail=exc.response.text,
            ) from exc
        except httpx.HTTPError:
            return None
        try:
            data = resp.json()
            unit_data = data.get("knowledge_unit", data) if isinstance(data, dict) else data
            return KnowledgeUnit.model_validate(unit_data)
        except (ValueError, ValidationError) as exc:
            raise RemoteError(
                status_code=resp.status_code,
                detail=f"Invalid response body: {exc}",
            ) from exc


def _db_path_from_env() -> Path | None:
    """Read local DB path from environment, or return None for default."""
    env_path = os.environ.get("CQ_LOCAL_DB_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return None


def _merge_results(
    local: list[KnowledgeUnit],
    remote: list[KnowledgeUnit],
    limit: int,
) -> list[KnowledgeUnit]:
    """Merge and deduplicate results, preferring local copies."""
    seen: set[str] = set()
    merged: list[KnowledgeUnit] = []
    for unit in [*local, *remote]:
        if unit.id not in seen:
            seen.add(unit.id)
            merged.append(unit)
    return merged[:limit]
