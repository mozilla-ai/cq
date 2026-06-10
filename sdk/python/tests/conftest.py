"""Shared test fixtures."""

import pytest

from cq.discovery import SUPPORTED_DISCOVERY_VERSION, NodeInfo


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Clear cq env vars and redirect the discovery cache so tests are isolated from the host."""
    monkeypatch.delenv("CQ_ADDR", raising=False)
    monkeypatch.delenv("CQ_API_KEY", raising=False)
    monkeypatch.delenv("CQ_LOCAL_DB_PATH", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("xdg_cache")))


class StaticResolver:
    """Test double that returns a default-shaped NodeInfo without HTTP or disk I/O.

    Synthesizes ``api_base_url = addr.rstrip("/") + "/api/v1"`` so test
    assertions written against the default discovery fallback continue
    to hold even when the Client is wired through a resolver.
    """

    def resolve(self, addr: str) -> NodeInfo:
        return NodeInfo(
            version=SUPPORTED_DISCOVERY_VERSION,
            api_base_url=addr.rstrip("/") + "/api/v1",
            api_version="v1",
        )

    def close(self) -> None:
        """No-op; the test double owns no resources."""


@pytest.fixture()
def static_resolver() -> StaticResolver:
    """Resolver test-double returning the default-shaped NodeInfo for every addr."""
    return StaticResolver()
