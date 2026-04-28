"""Tests for the shared FastAPI dependencies, including require_api_key."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from cq_server.api_keys import encode_token, generate_secret, hash_secret
from cq_server.deps import require_api_key


class _StubStore:
    """Minimal store stub exposing only the methods require_api_key calls."""

    def __init__(self, rows: dict[str, dict[str, Any]] | None = None) -> None:
        self.rows = rows or {}
        self.touched: list[str] = []

    async def get_active_api_key_by_id(self, key_id: str) -> dict[str, Any] | None:
        row = self.rows.get(key_id)
        if row is None or row.get("revoked_at") is not None:
            return None
        if datetime.fromisoformat(row["expires_at"]) <= datetime.now(UTC):
            return None
        return row

    async def touch_api_key_last_used(self, key_id: str) -> None:
        self.touched.append(key_id)


PEPPER = "test-pepper"


def _row(
    *,
    key_id: uuid.UUID,
    secret: str,
    username: str = "alice",
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "id": key_id.hex,
        "user_id": 1,
        "username": username,
        "name": "l",
        "labels": [],
        "key_prefix": secret[:8],
        "key_hash": hash_secret(secret, pepper=PEPPER),
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
def token_and_store() -> Iterator[tuple[str, _StubStore, uuid.UUID]]:
    key_id = uuid.uuid4()
    secret = generate_secret()
    token = encode_token(key_id=key_id, secret=secret)
    store = _StubStore({key_id.hex: _row(key_id=key_id, secret=secret)})
    yield token, store, key_id


class TestRequireApiKeyHappyPath:
    def test_valid_key_returns_username(self, token_and_store: tuple[str, _StubStore, uuid.UUID]) -> None:
        token, store, _ = token_and_store
        client = TestClient(_app_with_store(store))
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json() == {"username": "alice"}

    def test_valid_key_schedules_touch(self, token_and_store: tuple[str, _StubStore, uuid.UUID]) -> None:
        token, store, key_id = token_and_store
        client = TestClient(_app_with_store(store))
        client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert store.touched == [key_id.hex]


class TestRequireApiKeyRejections:
    def test_missing_header(self) -> None:
        client = TestClient(_app_with_store(_StubStore()))
        resp = client.get("/protected")
        assert resp.status_code == 401

    def test_wrong_scheme(self) -> None:
        client = TestClient(_app_with_store(_StubStore()))
        resp = client.get("/protected", headers={"Authorization": "Basic abc"})
        assert resp.status_code == 401

    def test_wrong_namespace(self) -> None:
        client = TestClient(_app_with_store(_StubStore()))
        token = f"sk.v1.{uuid.uuid4().hex}.sekret"
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_malformed_token(self) -> None:
        client = TestClient(_app_with_store(_StubStore()))
        resp = client.get("/protected", headers={"Authorization": "Bearer cqa_legacy"})
        assert resp.status_code == 401

    def test_unknown_key_id(self) -> None:
        client = TestClient(_app_with_store(_StubStore()))
        token = encode_token(key_id=uuid.uuid4(), secret=generate_secret())
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_wrong_secret(self) -> None:
        key_id = uuid.uuid4()
        stored_secret = generate_secret()
        store = _StubStore({key_id.hex: _row(key_id=key_id, secret=stored_secret)})
        presented_token = encode_token(key_id=key_id, secret=generate_secret())
        client = TestClient(_app_with_store(store))
        resp = client.get("/protected", headers={"Authorization": f"Bearer {presented_token}"})
        assert resp.status_code == 401

    def test_revoked_token(self) -> None:
        key_id = uuid.uuid4()
        secret = generate_secret()
        store = _StubStore({key_id.hex: _row(key_id=key_id, secret=secret, revoked_at=datetime.now(UTC))})
        token = encode_token(key_id=key_id, secret=secret)
        client = TestClient(_app_with_store(store))
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_expired_token(self) -> None:
        key_id = uuid.uuid4()
        secret = generate_secret()
        row = _row(key_id=key_id, secret=secret, expires_at=datetime.now(UTC) - timedelta(seconds=1))
        store = _StubStore({key_id.hex: row})
        token = encode_token(key_id=key_id, secret=secret)
        client = TestClient(_app_with_store(store))
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_missing_pepper_returns_500(self, token_and_store: tuple[str, _StubStore, uuid.UUID]) -> None:
        token, store, _ = token_and_store
        client = TestClient(_app_with_store(store, pepper=None))
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 500
