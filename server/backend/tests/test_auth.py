"""Tests for authentication module."""

import time
from collections.abc import Iterator
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from cq_server.app import app
from cq_server.auth import create_token, hash_password, verify_password, verify_token


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("CQ_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CQ_JWT_SECRET", "test-secret")
    with TestClient(app) as c:
        yield c


def _seed_user(client: TestClient, username: str = "peter", password: str = "secret123") -> None:
    """Seed a user directly via the store."""
    from cq_server.app import _get_store
    from cq_server.auth import hash_password

    store = _get_store()
    store.create_user(username, hash_password(password))


class TestPasswordHashing:
    def test_verify_correct_password(self) -> None:
        hashed = hash_password("secret123")
        assert verify_password("secret123", hashed) is True

    def test_verify_wrong_password(self) -> None:
        hashed = hash_password("secret123")
        assert verify_password("wrong", hashed) is False


class TestJWT:
    def test_create_and_verify_token(self) -> None:
        test_secret = "test-secret"  # pragma: allowlist secret
        token = create_token("peter", secret=test_secret, ttl_hours=24)
        payload = verify_token(token, secret=test_secret)
        assert payload["sub"] == "peter"

    def test_expired_token_rejected(self) -> None:
        test_secret = "test-secret"  # pragma: allowlist secret
        token = create_token("peter", secret=test_secret, ttl_hours=0)
        time.sleep(1)
        with pytest.raises(jwt.ExpiredSignatureError):
            verify_token(token, secret=test_secret)

    def test_invalid_token_rejected(self) -> None:
        test_secret = "test-secret"  # pragma: allowlist secret
        with pytest.raises(jwt.DecodeError):
            verify_token("not.a.token", secret=test_secret)

    def test_wrong_secret_rejected(self) -> None:
        secret_a = "secret-a"  # pragma: allowlist secret
        secret_b = "secret-b"  # pragma: allowlist secret
        token = create_token("peter", secret=secret_a)
        with pytest.raises(jwt.InvalidSignatureError):
            verify_token(token, secret=secret_b)


class TestLoginEndpoint:
    test_password = "secret123"  # pragma: allowlist secret

    def test_login_success(self, client: TestClient) -> None:
        _seed_user(client)
        resp = client.post("/auth/login", json={"username": "peter", "password": self.test_password})
        assert resp.status_code == 200
        body = resp.json()
        assert "token" in body
        assert body["username"] == "peter"

    def test_login_wrong_password(self, client: TestClient) -> None:
        _seed_user(client)
        resp = client.post(
            "/auth/login",
            json={"username": "peter", "password": "wrong"},  # pragma: allowlist secret
        )
        assert resp.status_code == 401

    def test_login_unknown_user(self, client: TestClient) -> None:
        resp = client.post("/auth/login", json={"username": "nobody", "password": self.test_password})
        assert resp.status_code == 401


class TestAuthMe:
    test_password = "secret123"  # pragma: allowlist secret

    def test_me_with_valid_token(self, client: TestClient) -> None:
        _seed_user(client)
        login = client.post("/auth/login", json={"username": "peter", "password": self.test_password})
        token = login.json()["token"]
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["username"] == "peter"

    def test_me_without_token(self, client: TestClient) -> None:
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_me_with_invalid_token(self, client: TestClient) -> None:
        resp = client.get("/auth/me", headers={"Authorization": "Bearer invalid"})
        assert resp.status_code == 401
