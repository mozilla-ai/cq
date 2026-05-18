"""Resolver: turn a cq node address into a NodeInfo.

The resolver probes the node's discovery document at WELL_KNOWN_PATH,
falls back to documented defaults when the node does not publish a discovery document,
memoizes successful results in process,
and persists them through a Cache so short-lived processes share state across invocations.

NOTE: Resolver is safe for concurrent use; the in-process memo is guarded
by a threading.Lock and the on-disk cache is fronted by atomic temp-file
plus rename.

NOTE: callers must treat DiscoveryError as the resolver's single failure
channel.
Transport exhaustion, malformed bodies, schema mismatches, and unexpected
status codes all surface as DiscoveryError so the Client's FallbackError
logic can distinguish operator/client misconfiguration from connectivity
failures uniformly.
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx
from pydantic import ValidationError

from ._cache import Cache
from ._types import (
    DEFAULT_API_PATH,
    DEFAULT_API_VERSION,
    DEFAULT_CACHE_TTL_SECONDS,
    SUPPORTED_DISCOVERY_VERSION,
    WELL_KNOWN_PATH,
    NodeInfo,
)
from ._validate import validate as _validate_info

_DEFAULT_LOGGER = logging.getLogger("cq.discovery")
_DEFAULT_TIMEOUT = 5.0
_RETRY_ATTEMPTS = 2
_RETRY_BACKOFF_SECONDS = 0.2
_MAX_BODY_BYTES = 64 * 1024


class DiscoveryError(Exception):
    """Raised when the discovery probe fails for any non-recoverable reason.

    Misconfigured responses (HTML pages, malformed JSON, unknown fields,
    schema/api version mismatches, hostless or non-http api_base_urls) and
    transport failures that survive the retry budget all surface as
    DiscoveryError so a single exception type covers resolver-layer
    failure.

    NOTE: distinct from httpx.HTTPError so the Client's FallbackError
    logic can treat resolver failures separately from per-call HTTP
    failures.
    """


class Resolver:
    """Map a cq node address to a NodeInfo by probing the node's discovery document at WELL_KNOWN_PATH.

    When the node does not publish a discovery document, the documented
    defaults (`addr + DEFAULT_API_PATH`, `DEFAULT_API_VERSION`) are
    returned.
    A valid discovery response yields a parsed NodeInfo whose
    `api_base_url` is taken verbatim from the document.
    Every other shape (text/html, malformed JSON, schema or api version
    mismatch, hostless or non-http api_base_url, retry-exhausted transport
    failure) raises DiscoveryError.

    Successful resolutions are memoized in-process for the lifetime of
    the Resolver and, when a cache_dir is configured, persisted to disk
    so short-lived processes share results across invocations.

    NOTE: instances are safe for concurrent use;
    concurrent resolve() calls for the same address are coalesced into a single probe (single-flight).
    """

    def __init__(
        self,
        cache_dir: Path | None,
        http_client: httpx.Client | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Build a Resolver with the given on-disk cache location and HTTP transport.

        `cache_dir=None` disables on-disk caching;
        the in-process memo still applies.
        `http_client` defaults to a fresh `httpx.Client` so callers do not
        need to wire one for the default code path.
        `logger` defaults to `logging.getLogger("cq.discovery")`.
        NOTE: this module does not install a NullHandler;
        the Client layer is responsible for taming the cq logger tree.
        """
        self._cache = Cache(cache_dir=cache_dir, ttl_seconds=DEFAULT_CACHE_TTL_SECONDS)
        self._http: httpx.Client = http_client if http_client is not None else httpx.Client(timeout=_DEFAULT_TIMEOUT)
        self._owns_http: bool = http_client is None
        self._logger = logger if logger is not None else _DEFAULT_LOGGER
        self._lock = threading.Lock()
        self._mem: dict[str, NodeInfo] = {}
        self._inflight: dict[str, concurrent.futures.Future[NodeInfo]] = {}

    def close(self) -> None:
        """Release resources owned by this Resolver.

        Closes the underlying httpx.Client only when this Resolver created it.
        A client passed in by the caller is the caller's to close.
        """
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> Resolver:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def resolve(self, addr: str) -> NodeInfo:
        """Return the NodeInfo for addr, probing the network only when no cached entry is available.

        Trailing slashes in addr are normalized away before lookup so
        `https://node.example.com` and `https://node.example.com/` share
        a cache entry.
        Concurrent callers for the same address are coalesced (single-flight):
        the first caller probes, every other caller waits for that probe's result
        and sees the same NodeInfo (or the same DiscoveryError).
        Disk-cache write failures are logged at warning level and
        otherwise swallowed:
        the resolution itself remains valid for the lifetime of this
        process.
        """
        addr = addr.rstrip("/")

        with self._lock:
            cached = self._mem.get(addr)
            if cached is not None:
                return cached
            future = self._inflight.get(addr)
            if future is not None:
                elected = False
            else:
                future = concurrent.futures.Future()
                self._inflight[addr] = future
                elected = True

        if not elected:
            # Waiters block outside the lock so the elected prober can make progress.
            return future.result()

        try:
            result = self._resolve_uncached(addr)
        except BaseException as exc:
            with self._lock:
                self._inflight.pop(addr, None)
            future.set_exception(exc)
            raise
        else:
            with self._lock:
                self._mem[addr] = result
                self._inflight.pop(addr, None)
            future.set_result(result)
            return result

    def _resolve_uncached(self, addr: str) -> NodeInfo:
        """Run the disk-cache check and network probe for addr.

        NOTE: callers must own the single-flight election;
        this helper does no in-process memoization and is not safe to call directly
        outside the resolve() flow.
        """
        from_disk = self._cache.get(addr)
        if from_disk is not None:
            return from_disk

        info = self._probe(addr)
        try:
            self._cache.put(addr, info)
        except OSError as err:
            self._logger.warning("discovery: cache write failed for %s: %s", addr, err)
        return info

    def _probe(self, addr: str) -> NodeInfo:
        """Fetch the discovery document for addr and turn it into a NodeInfo.

        When the node does not publish a discovery document, the documented defaults are returned
        so an unconfigured node remains reachable.
        Any unexpected response, an HTML body, malformed JSON, an unknown field,
        or a schema/api version mismatch becomes a DiscoveryError rather than a silent fallback.
        """
        url = _join_well_known(addr)
        try:
            response = self._fetch_with_retry(url)
        except httpx.HTTPError as err:
            raise DiscoveryError(f"discovery: probe failed after {_RETRY_ATTEMPTS} attempts: {err}") from err

        if response.status_code == 404:
            return _defaults_for(addr)
        if response.status_code != 200:
            raise DiscoveryError(f"discovery: unexpected status {response.status_code} from {url}")

        content_type = response.headers.get("Content-Type", "")
        if content_type.lower().startswith("text/html"):
            raise DiscoveryError(
                f"discovery: {addr} returned text/html — the address likely points at a SPA, not a cq node API"
            )

        body = response.content[:_MAX_BODY_BYTES]
        try:
            info = NodeInfo.model_validate_json(body)
        except ValidationError as err:
            details = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in err.errors())
            raise DiscoveryError(f"discovery: parse body: {details}") from err

        try:
            _validate_info(info)
        except ValueError as err:
            raise DiscoveryError(f"discovery: {err}") from err
        return info

    def _fetch_with_retry(self, url: str) -> httpx.Response:
        """Issue a GET to url, retrying transport errors and server-side failures up to the configured attempt budget.

        Client-side responses are returned without retry so a node that does not publish a discovery document
        remains observable in one attempt.
        The backoff is linear and short:
        attempt `i` (1-indexed) sleeps `i * _RETRY_BACKOFF_SECONDS`
        before issuing the request.
        """
        last_error: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            if attempt > 0:
                time.sleep(attempt * _RETRY_BACKOFF_SECONDS)
            try:
                response = self._http.get(url, headers={"Accept": "application/json"})
            except httpx.HTTPError as err:
                last_error = err
                continue
            if response.status_code >= 500:
                last_error = httpx.HTTPStatusError(
                    f"status {response.status_code}", request=response.request, response=response
                )
                continue
            return response
        if last_error is None:
            raise RuntimeError("retry budget exhausted without recording a failure")
        raise last_error


def _defaults_for(addr: str) -> NodeInfo:
    """Return the NodeInfo applied when a node does not publish a discovery document.

    The api_base_url is `addr + DEFAULT_API_PATH`, the api_version is
    `DEFAULT_API_VERSION`, and the document schema version is
    `SUPPORTED_DISCOVERY_VERSION`.
    """
    return NodeInfo(
        version=SUPPORTED_DISCOVERY_VERSION,
        api_base_url=addr + DEFAULT_API_PATH,
        api_version=DEFAULT_API_VERSION,
    )


def _join_well_known(addr: str) -> str:
    """Append WELL_KNOWN_PATH to addr's existing path rather than replacing it.

    Addresses like `https://node.example.com/cq` keep their `/cq` prefix
    so the probe lands at `/cq/.well-known/cq-node.json`.
    """
    parsed = urlparse(addr)
    base_path = parsed.path.rstrip("/")
    new_path = base_path + WELL_KNOWN_PATH
    return urlunparse(parsed._replace(path=new_path))
