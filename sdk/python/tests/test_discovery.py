"""Tests for the node-discovery Resolver.

HTTP interactions are mocked with httpx.MockTransport rather than
`pytest-httpx` so the SDK does not gain a new test dependency.
The transport closure records call counts and sequences per-request
responses, which is enough to mirror Go's `httptest.NewServer` pattern
used in the upstream resolver test set.
"""

from __future__ import annotations

import concurrent.futures
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import cq_schema
import httpx
import jsonschema
import pytest

from cq.discovery._resolver import DiscoveryError, Resolver
from cq.discovery._types import (
    DEFAULT_API_PATH,
    DEFAULT_API_VERSION,
    SUPPORTED_DISCOVERY_VERSION,
    WELL_KNOWN_PATH,
    NodeInfo,
)

_VALID_DOC = {
    "version": 1,
    "api_base_url": "https://api.example.com/api/v1",
    "api_version": "v1",
    "node_name": "example",
}


def _addr() -> str:
    """Return the placeholder node address used by every test."""
    return "https://node.example.com"


def _json_response(payload: Any, status_code: int = 200) -> httpx.Response:
    """Build an httpx.Response carrying a JSON body and Content-Type."""
    return httpx.Response(
        status_code=status_code,
        headers={"Content-Type": "application/json"},
        content=json.dumps(payload).encode("utf-8"),
    )


def _raw_response(body: bytes, *, content_type: str, status_code: int = 200) -> httpx.Response:
    """Build an httpx.Response with a caller-supplied body and Content-Type."""
    return httpx.Response(
        status_code=status_code,
        headers={"Content-Type": content_type},
        content=body,
    )


class _Recorder:
    """Capture every well-known probe and serve scripted responses.

    The handler is invoked once per outbound request.
    `calls` is the running request count so tests can pin retry counts.
    """

    def __init__(self, handler: Callable[[int, httpx.Request], httpx.Response]) -> None:
        self.calls = 0
        self._handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return self._handler(self.calls, request)


def _client_with(recorder: _Recorder) -> httpx.Client:
    """Build an httpx.Client whose transport routes every request through recorder."""
    return httpx.Client(transport=httpx.MockTransport(recorder))


def _resolver(
    cache_dir: Path | None,
    recorder: _Recorder | None = None,
) -> Resolver:
    """Build a Resolver wired to a MockTransport client."""
    http_client = _client_with(recorder) if recorder is not None else httpx.Client()
    return Resolver(cache_dir=cache_dir, http_client=http_client)


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace time.sleep inside the resolver module with a recorder.

    The list of recorded durations is reachable via request.getfixturevalue
    for the few tests that pin retry backoff; everyone else gets a fast
    suite for free.
    """
    calls: list[float] = []

    def _record(seconds: float) -> None:
        calls.append(seconds)

    from cq.discovery import _resolver as resolver_module

    monkeypatch.setattr(resolver_module.time, "sleep", _record)
    return calls


class TestResolveAcceptsValidDocument:
    def test_returns_parsed_node_info(self, tmp_path: Path) -> None:
        def handler(_call: int, request: httpx.Request) -> httpx.Response:
            assert request.url.path == WELL_KNOWN_PATH
            return _json_response(_VALID_DOC)

        recorder = _Recorder(handler)
        info = _resolver(tmp_path, recorder).resolve(_addr())
        assert info.version == SUPPORTED_DISCOVERY_VERSION
        assert info.api_base_url == "https://api.example.com/api/v1"
        assert info.api_version == "v1"
        assert info.node_name == "example"


class TestResolveCachesOnDiskAcrossInstances:
    def test_second_resolver_does_not_probe(self, tmp_path: Path) -> None:
        recorder = _Recorder(lambda _c, _r: _json_response({}, status_code=404))
        first = _resolver(tmp_path, recorder)
        first.resolve(_addr())
        assert recorder.calls == 1

        # A fresh Resolver pointed at the same cache directory must serve
        # the prior result from disk and issue zero new requests.
        recorder.calls = 0
        second = _resolver(tmp_path, recorder)
        info = second.resolve(_addr())
        assert recorder.calls == 0
        assert info.api_base_url == _addr() + DEFAULT_API_PATH


class TestResolveCachesSuccessInProcess:
    def test_second_call_does_no_http(self, tmp_path: Path) -> None:
        recorder = _Recorder(lambda _c, _r: _json_response(_VALID_DOC))
        resolver = _resolver(tmp_path, recorder)
        first = resolver.resolve(_addr())
        second = resolver.resolve(_addr())
        assert recorder.calls == 1
        assert first == second


class TestResolveFallsBackOn404:
    def test_returns_defaults_and_caches(self, tmp_path: Path) -> None:
        recorder = _Recorder(lambda _c, _r: _json_response({"detail": "not found"}, status_code=404))
        resolver = _resolver(tmp_path, recorder)
        info = resolver.resolve(_addr())
        assert info.version == SUPPORTED_DISCOVERY_VERSION
        assert info.api_base_url == _addr() + DEFAULT_API_PATH
        assert info.api_version == DEFAULT_API_VERSION

        # Second call is served by the in-process memo.
        resolver.resolve(_addr())
        assert recorder.calls == 1


class TestResolveNormalizesTrailingSlash:
    def test_trailing_slash_in_addr_is_stripped(self, tmp_path: Path) -> None:
        recorder = _Recorder(lambda _c, _r: _json_response({}, status_code=404))
        resolver = _resolver(tmp_path, recorder)
        info = resolver.resolve(_addr() + "/")
        assert info.api_base_url == _addr() + DEFAULT_API_PATH


class TestResolveRejectsExtraField:
    def test_unknown_field_raises(self, tmp_path: Path) -> None:
        payload = dict(_VALID_DOC) | {"made_up_field": "x"}
        recorder = _Recorder(lambda _c, _r: _json_response(payload))
        resolver = _resolver(tmp_path, recorder)
        with pytest.raises(DiscoveryError) as exc:
            resolver.resolve(_addr())
        assert "made_up_field" in str(exc.value).lower()

        # Failed probes must not be cached.
        with pytest.raises(DiscoveryError):
            resolver.resolve(_addr())
        assert recorder.calls == 2


class TestResolveRejectsHostlessApiBaseUrl:
    def test_missing_host_raises(self, tmp_path: Path) -> None:
        payload = {
            "version": 1,
            "api_base_url": "https://",
            "api_version": "v1",
        }
        recorder = _Recorder(lambda _c, _r: _json_response(payload))
        resolver = _resolver(tmp_path, recorder)
        with pytest.raises(DiscoveryError) as exc:
            resolver.resolve(_addr())
        assert "host" in str(exc.value).lower()

        with pytest.raises(DiscoveryError):
            resolver.resolve(_addr())
        assert recorder.calls == 2


class TestResolveRejectsInvalidPortApiBaseUrl:
    def test_non_numeric_port_raises(self, tmp_path: Path) -> None:
        payload = {
            "version": 1,
            "api_base_url": "https://example.com:bad/api/v1",
            "api_version": "v1",
        }
        recorder = _Recorder(lambda _c, _r: _json_response(payload))
        resolver = _resolver(tmp_path, recorder)
        with pytest.raises(DiscoveryError) as exc:
            resolver.resolve(_addr())
        assert "port" in str(exc.value).lower()

        with pytest.raises(DiscoveryError):
            resolver.resolve(_addr())
        assert recorder.calls == 2


class TestResolveRejectsHtml:
    def test_text_html_mentions_spa(self, tmp_path: Path) -> None:
        recorder = _Recorder(
            lambda _c, _r: _raw_response(
                b"<!doctype html><html>...</html>",
                content_type="text/html; charset=utf-8",
            )
        )
        resolver = _resolver(tmp_path, recorder)
        with pytest.raises(DiscoveryError) as exc:
            resolver.resolve(_addr())
        assert "SPA" in str(exc.value)

        with pytest.raises(DiscoveryError):
            resolver.resolve(_addr())
        assert recorder.calls == 2
        # Regression sentinel: failed probes must not poison the on-disk cache.
        assert list(tmp_path.iterdir()) == []


class TestResolveRejectsMalformedJson:
    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        recorder = _Recorder(lambda _c, _r: _raw_response(b"{not valid", content_type="application/json"))
        resolver = _resolver(tmp_path, recorder)
        with pytest.raises(DiscoveryError):
            resolver.resolve(_addr())

        with pytest.raises(DiscoveryError):
            resolver.resolve(_addr())
        assert recorder.calls == 2

    def test_trailing_content_raises(self, tmp_path: Path) -> None:
        body = json.dumps(_VALID_DOC).encode("utf-8") + b" garbage"
        recorder = _Recorder(lambda _c, _r: _raw_response(body, content_type="application/json"))
        resolver = _resolver(tmp_path, recorder)
        with pytest.raises(DiscoveryError) as exc:
            resolver.resolve(_addr())
        assert "trailing" in str(exc.value).lower()


class TestResolveRejectsMismatchedApiVersion:
    def test_v2_names_both_versions(self, tmp_path: Path) -> None:
        payload = dict(_VALID_DOC) | {"api_version": "v2"}
        recorder = _Recorder(lambda _c, _r: _json_response(payload))
        resolver = _resolver(tmp_path, recorder)
        with pytest.raises(DiscoveryError) as exc:
            resolver.resolve(_addr())
        message = str(exc.value)
        assert "v1" in message
        assert "v2" in message

        with pytest.raises(DiscoveryError):
            resolver.resolve(_addr())
        assert recorder.calls == 2


class TestResolveRejectsMismatchedDiscoveryVersion:
    def test_version_2_names_both_versions(self, tmp_path: Path) -> None:
        payload = dict(_VALID_DOC) | {"version": 2}
        recorder = _Recorder(lambda _c, _r: _json_response(payload))
        resolver = _resolver(tmp_path, recorder)
        with pytest.raises(DiscoveryError) as exc:
            resolver.resolve(_addr())
        message = str(exc.value)
        assert "1" in message
        assert "2" in message

        with pytest.raises(DiscoveryError):
            resolver.resolve(_addr())
        assert recorder.calls == 2


class TestResolveRejectsMissingDiscoveryVersion:
    def test_absent_version_field_raises(self, tmp_path: Path) -> None:
        payload = {k: v for k, v in _VALID_DOC.items() if k != "version"}
        recorder = _Recorder(lambda _c, _r: _json_response(payload))
        resolver = _resolver(tmp_path, recorder)
        with pytest.raises(DiscoveryError):
            resolver.resolve(_addr())

        with pytest.raises(DiscoveryError):
            resolver.resolve(_addr())
        assert recorder.calls == 2


class TestResolveRejectsNonHttpScheme:
    def test_ftp_url_raises_mentions_scheme(self, tmp_path: Path) -> None:
        payload = dict(_VALID_DOC) | {"api_base_url": "ftp://example.com/api/v1"}
        recorder = _Recorder(lambda _c, _r: _json_response(payload))
        resolver = _resolver(tmp_path, recorder)
        with pytest.raises(DiscoveryError) as exc:
            resolver.resolve(_addr())
        assert "scheme" in str(exc.value).lower()

        with pytest.raises(DiscoveryError):
            resolver.resolve(_addr())
        assert recorder.calls == 2


class TestResolveRetriesOn5xx:
    def test_two_5xx_responses_raises_after_two_calls(self, tmp_path: Path, _fast_sleep: list[float]) -> None:
        recorder = _Recorder(lambda _c, _r: _raw_response(b"boom", content_type="text/plain", status_code=500))
        resolver = _resolver(tmp_path, recorder)
        with pytest.raises(DiscoveryError):
            resolver.resolve(_addr())
        assert recorder.calls == 2
        # One backoff between two attempts.
        assert _fast_sleep == [0.2]


class TestResolveRetriesOnTransportError:
    def test_two_transport_errors_raises_after_two_calls(self, tmp_path: Path, _fast_sleep: list[float]) -> None:
        def handler(_call: int, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        recorder = _Recorder(handler)
        resolver = _resolver(tmp_path, recorder)
        with pytest.raises(DiscoveryError):
            resolver.resolve(_addr())
        assert recorder.calls == 2
        assert _fast_sleep == [0.2]


class TestResolveWithoutDiskCache:
    def test_empty_cache_dir_still_resolves(self, tmp_path: Path) -> None:
        recorder = _Recorder(lambda _c, _r: _json_response(_VALID_DOC))
        # cache_dir=None disables the on-disk cache; tmp_path is here only
        # to give the test a workspace, and it must stay empty.
        resolver = _resolver(cache_dir=None, recorder=recorder)
        info = resolver.resolve(_addr())
        assert info.api_base_url == "https://api.example.com/api/v1"
        assert list(tmp_path.iterdir()) == []


class TestResolverClose:
    def test_close_leaves_caller_supplied_client_open(self, tmp_path: Path) -> None:
        recorder = _Recorder(lambda _c, _r: _json_response(_VALID_DOC))
        http = _client_with(recorder)
        resolver = Resolver(cache_dir=tmp_path, http_client=http)
        resolver.close()
        # The caller still owns the client and can keep using it.
        info = NodeInfo.model_validate_json(http.get("https://node.example.com" + WELL_KNOWN_PATH).content)
        assert info.api_version == "v1"
        http.close()

    def test_close_is_safe_when_resolver_owns_client(self, tmp_path: Path) -> None:
        resolver = Resolver(cache_dir=tmp_path)
        resolver.close()
        assert resolver._http.is_closed


class TestSchemaContractMatchesFixtures:
    """Cross-ecosystem pin: the synced node_discovery schema must accept every fixture.

    If Go adds a field to the schema without Python re-running sync-schema,
    or if a fixture drifts from the schema, this test fails fast and forces
    both ecosystems to land the change together.
    """

    def test_fixtures_match_schema(self) -> None:
        schema = cq_schema.load_schema("node_discovery")
        fixtures_dir = Path(__file__).resolve().parents[3] / "schema" / "fixtures"
        minimal = json.loads((fixtures_dir / "node_discovery_minimal.json").read_bytes())
        split = json.loads((fixtures_dir / "node_discovery_split.json").read_bytes())
        invalid = json.loads((fixtures_dir / "node_discovery_invalid_version.json").read_bytes())

        jsonschema.validate(minimal, schema)
        jsonschema.validate(split, schema)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_minimal_fixture_resolves_as_node_info(self) -> None:
        fixtures_dir = Path(__file__).resolve().parents[3] / "schema" / "fixtures"
        raw = (fixtures_dir / "node_discovery_minimal.json").read_bytes()
        info = NodeInfo.model_validate_json(raw)
        assert info.version == SUPPORTED_DISCOVERY_VERSION
        assert info.api_version == "v1"


class _ConcurrentRecorder:
    """Thread-safe recorder used by the single-flight tests.

    Tracks call count under a lock so concurrent transport invocations stay observable,
    signals first-call arrival before parking on an optional gate, and only then
    invokes the supplied handler. The signal-before-park layout lets a test wait until
    the elected prober is provably inside the transport before releasing the gate.
    """

    def __init__(
        self,
        handler: Callable[[int, httpx.Request], httpx.Response],
        gate: threading.Event | None = None,
        arrived: threading.Event | None = None,
    ) -> None:
        self.calls = 0
        self._handler = handler
        self._gate = gate
        self._arrived = arrived
        self._lock = threading.Lock()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        with self._lock:
            self.calls += 1
            this_call = self.calls
        # Signal arrival before parking so the test can wait for the elected prober
        # to be observably inside the transport.
        if self._arrived is not None and this_call == 1:
            self._arrived.set()
        # The gate is owned by the test; only the first call waits on it
        # so the elected prober can be parked while waiters pile up.
        if self._gate is not None and this_call == 1:
            assert self._gate.wait(timeout=5.0)
        return self._handler(this_call, request)


def _concurrent_resolver(
    tmp_path: Path,
    recorder: _ConcurrentRecorder,
) -> Resolver:
    """Build a Resolver wired to a MockTransport that routes through the concurrent recorder."""
    http_client = httpx.Client(transport=httpx.MockTransport(recorder))
    return Resolver(cache_dir=tmp_path, http_client=http_client)


def _wait_for_inflight_waiter(resolver: Resolver, addr: str, timeout: float = 5.0) -> None:
    """Block until at least one thread is parked on the single-flight future for addr.

    Spins on the futures Condition's internal waiter deque to avoid sleep-based pacing;
    each waiter inside Condition.wait() leaves a lock object on `_condition._waiters`,
    so a non-empty deque proves at least one thread is parked on future.result().
    """
    deadline = threading.Event()
    timer = threading.Timer(timeout, deadline.set)
    timer.start()
    try:
        while not deadline.is_set():
            with resolver._lock:  # noqa: SLF001 — test introspection
                future = resolver._inflight.get(addr)  # noqa: SLF001
            if future is not None:
                condition = future._condition  # noqa: SLF001
                if condition._waiters:  # noqa: SLF001
                    return
        raise AssertionError(f"timed out waiting for an inflight waiter on {addr!r}")
    finally:
        timer.cancel()


class TestResolverSingleFlight:
    def test_concurrent_resolves_same_addr_share_one_probe(self, tmp_path: Path) -> None:
        gate = threading.Event()
        arrived = threading.Event()

        def handler(_call: int, _request: httpx.Request) -> httpx.Response:
            return _json_response(_VALID_DOC)

        recorder = _ConcurrentRecorder(handler, gate=gate, arrived=arrived)
        resolver = _concurrent_resolver(tmp_path, recorder)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(resolver.resolve, _addr())
            # Wait until the elected prober is parked on the gate before submitting the second worker.
            assert arrived.wait(timeout=5.0)
            f2 = pool.submit(resolver.resolve, _addr())
            # Make sure the second worker has registered as a waiter on the in-flight future
            # before the elected prober's response lands.
            _wait_for_inflight_waiter(resolver, _addr())
            gate.set()
            info_a = f1.result(timeout=5.0)
            info_b = f2.result(timeout=5.0)

        assert recorder.calls == 1
        assert info_a == info_b
        assert info_a.api_base_url == "https://api.example.com/api/v1"

    def test_concurrent_resolves_different_addrs_probe_independently(self, tmp_path: Path) -> None:
        addr_one = "https://one.example.com"
        addr_two = "https://two.example.com"
        payload_one = dict(_VALID_DOC) | {"api_base_url": "https://api-one.example.com/api/v1"}
        payload_two = dict(_VALID_DOC) | {"api_base_url": "https://api-two.example.com/api/v1"}

        def handler(_call: int, request: httpx.Request) -> httpx.Response:
            host = request.url.host
            if host == "one.example.com":
                return _json_response(payload_one)
            if host == "two.example.com":
                return _json_response(payload_two)
            raise AssertionError(f"unexpected host {host!r}")

        recorder = _ConcurrentRecorder(handler)
        resolver = _concurrent_resolver(tmp_path, recorder)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(resolver.resolve, addr_one)
            f2 = pool.submit(resolver.resolve, addr_two)
            info_one = f1.result(timeout=5.0)
            info_two = f2.result(timeout=5.0)

        assert recorder.calls == 2
        assert info_one.api_base_url == "https://api-one.example.com/api/v1"
        assert info_two.api_base_url == "https://api-two.example.com/api/v1"

    def test_concurrent_resolves_propagate_probe_failure(self, tmp_path: Path) -> None:
        gate = threading.Event()
        arrived = threading.Event()

        def handler(_call: int, _request: httpx.Request) -> httpx.Response:
            return _raw_response(
                b"<!doctype html><html>...</html>",
                content_type="text/html; charset=utf-8",
            )

        recorder = _ConcurrentRecorder(handler, gate=gate, arrived=arrived)
        resolver = _concurrent_resolver(tmp_path, recorder)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(resolver.resolve, _addr())
            assert arrived.wait(timeout=5.0)
            f2 = pool.submit(resolver.resolve, _addr())
            _wait_for_inflight_waiter(resolver, _addr())
            gate.set()
            for fut in (f1, f2):
                with pytest.raises(DiscoveryError):
                    fut.result(timeout=5.0)

        assert recorder.calls == 1

    def test_failed_probe_does_not_memoize_for_next_caller(self, tmp_path: Path) -> None:
        def handler(_call: int, _request: httpx.Request) -> httpx.Response:
            return _raw_response(
                b"<!doctype html><html>...</html>",
                content_type="text/html; charset=utf-8",
            )

        recorder = _ConcurrentRecorder(handler)
        resolver = _concurrent_resolver(tmp_path, recorder)

        with pytest.raises(DiscoveryError):
            resolver.resolve(_addr())
        with pytest.raises(DiscoveryError):
            resolver.resolve(_addr())
        assert recorder.calls == 2
