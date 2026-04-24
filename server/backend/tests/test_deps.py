"""Tests for the shared FastAPI dependencies, including require_api_key."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from cq_server.api_keys import hash_token
from cq_server.deps import require_api_key


class _StubStore:
    """Minimal store stub exposing only the methods require_api_key calls."""

    def __init__(self, rows: dict[str, dict[str, Any]] | None = None) -> None:
        self.rows = rows or {}
        self.touched: list[str] = []

    def get_api_key_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        return self.rows.get(key_hash)

    def touch_api_key_last_used(self, key_id: str) -> None:
        self.touched.append(key_id)


PEPPER = "test-pepper"


def _row(
    *,
    key_id: str = "k1",
    username: str = "alice",
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "id": key_id,
        "user_id": 1,
        "username": username,
        "name": "l",
        "labels": [],
        "key_prefix": "cqa_abcd",
        "ttl": "30d",
        "expires_at": (expires_at or datetime.now(UTC) + timedelta(days=30)).isoformat(),
        "created_at": datetime.now(UTC).isoformat(),
        "last_used_at": None,
        "revoked_at": revoked_at.isoformat() if revoked_at else None,
    }


def _app_with_store(store: _StubStore, *, pepper: str | None = PEPPER) -> FastAPI:
    app = FastAPI()
    app.state.store = store
    if pepper is not None:
        app.state.api_key_pepper = pepper

    @app.get("/protected")
    def protected(username: str = Depends(require_api_key)) -> dict[str, str]:
        return {"username": username}

    return app


@pytest.fixture()
def token_and_store() -> Iterator[tuple[str, _StubStore]]:
    plaintext = "cqa_exampletoken"
    digest = hash_token(plaintext, pepper=PEPPER)
    store = _StubStore({digest: _row()})
    yield plaintext, store


class TestRequireApiKeyHappyPath:
    def test_valid_key_returns_username(self, token_and_store: tuple[str, _StubStore]) -> None:
        token, store = token_and_store
        client = TestClient(_app_with_store(store))
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json() == {"username": "alice"}

    def test_valid_key_schedules_touch(self, token_and_store: tuple[str, _StubStore]) -> None:
        token, store = token_and_store
        client = TestClient(_app_with_store(store))
        client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert store.touched == ["k1"]


class TestRequireApiKeyRejections:
    def test_missing_header(self) -> None:
        client = TestClient(_app_with_store(_StubStore()))
        resp = client.get("/protected")
        assert resp.status_code == 401

    def test_wrong_scheme(self) -> None:
        client = TestClient(_app_with_store(_StubStore()))
        resp = client.get("/protected", headers={"Authorization": "Basic abc"})
        assert resp.status_code == 401

    def test_wrong_prefix(self) -> None:
        client = TestClient(_app_with_store(_StubStore()))
        resp = client.get("/protected", headers={"Authorization": "Bearer sk-something"})
        assert resp.status_code == 401

    def test_unknown_token(self) -> None:
        client = TestClient(_app_with_store(_StubStore()))
        resp = client.get("/protected", headers={"Authorization": "Bearer cqa_unknown"})
        assert resp.status_code == 401

    def test_revoked_token(self) -> None:
        token = "cqa_revokedtoken"
        digest = hash_token(token, pepper=PEPPER)
        store = _StubStore({digest: _row(revoked_at=datetime.now(UTC))})
        client = TestClient(_app_with_store(store))
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_expired_token(self) -> None:
        token = "cqa_expiredtoken"
        digest = hash_token(token, pepper=PEPPER)
        store = _StubStore({digest: _row(expires_at=datetime.now(UTC) - timedelta(seconds=1))})
        client = TestClient(_app_with_store(store))
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_missing_pepper_returns_500(self, token_and_store: tuple[str, _StubStore]) -> None:
        token, store = token_and_store
        client = TestClient(_app_with_store(store, pepper=None))
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 500
