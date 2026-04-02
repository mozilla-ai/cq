"""Shared test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear CQ environment variables so tests are isolated from the host."""
    monkeypatch.delenv("CQ_ADDR", raising=False)
    monkeypatch.delenv("CQ_API_KEY", raising=False)
    monkeypatch.delenv("CQ_LOCAL_DB_PATH", raising=False)
