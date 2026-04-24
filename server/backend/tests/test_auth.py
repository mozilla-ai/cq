"""Tests for authentication module."""

import time
from collections.abc import Iterator
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from cq_server.app import app
from cq_server.auth import create_token, hash_password, verify_password, verify_token
from cq_server.deps import require_api_key


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("CQ_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CQ_JWT_SECRET", "test-secret")
    monkeypatch.setenv("CQ_API_KEY_PEPPER", "test-pepper")
    app.dependency_overrides[require_api_key] = lambda: "test-user"
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(require_api_key, None)


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


@pytest.fixture()
def api_key_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Client fixture with real API key enforcement (no dep override)."""
    monkeypatch.setenv("CQ_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CQ_JWT_SECRET", "test-secret")
    monkeypatch.setenv("CQ_API_KEY_PEPPER", "test-pepper")
    app.dependency_overrides.pop(require_api_key, None)
    with TestClient(app) as c:
        yield c


def _login(client: TestClient, username: str = "peter", password: str = "secret123") -> str:
    _seed_user(client, username=username, password=password)
    resp = client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["token"]


class TestApiKeyCreate:
    def test_create_returns_plaintext_once(self, api_key_client: TestClient) -> None:
        token = _login(api_key_client)
        resp = api_key_client.post(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "laptop", "ttl": "30d"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["token"].startswith("cqa_")
        assert body["name"] == "laptop"
        assert body["prefix"].startswith("cqa_")
        assert body["is_active"] is True
        assert body["is_expired"] is False

    def test_create_requires_jwt(self, api_key_client: TestClient) -> None:
        resp = api_key_client.post("/auth/api-keys", json={"name": "x", "ttl": "30d"})
        assert resp.status_code == 401

    def test_create_rejects_invalid_ttl(self, api_key_client: TestClient) -> None:
        token = _login(api_key_client)
        resp = api_key_client.post(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "x", "ttl": "3mo"},
        )
        assert resp.status_code == 422

    def test_create_rejects_empty_name(self, api_key_client: TestClient) -> None:
        token = _login(api_key_client)
        resp = api_key_client.post(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "", "ttl": "30d"},
        )
        assert resp.status_code == 422

    def test_create_hits_max_active_cap(self, api_key_client: TestClient) -> None:
        token = _login(api_key_client)
        for i in range(20):
            resp = api_key_client.post(
                "/auth/api-keys",
                headers={"Authorization": f"Bearer {token}"},
                json={"name": f"k{i}", "ttl": "30d"},
            )
            assert resp.status_code == 201
        resp = api_key_client.post(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "k21", "ttl": "30d"},
        )
        assert resp.status_code == 409


class TestApiKeyList:
    def test_list_hides_plaintext(self, api_key_client: TestClient) -> None:
        token = _login(api_key_client)
        api_key_client.post(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "laptop", "ttl": "30d"},
        )
        resp = api_key_client.get("/auth/api-keys", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        keys = resp.json()
        assert len(keys) == 1
        assert "token" not in keys[0]
        assert keys[0]["name"] == "laptop"

    def test_list_requires_jwt(self, api_key_client: TestClient) -> None:
        resp = api_key_client.get("/auth/api-keys")
        assert resp.status_code == 401

    def test_list_scoped_to_caller(self, api_key_client: TestClient) -> None:
        token_a = _login(api_key_client, username="alice")
        token_b = _login(api_key_client, username="bob")
        api_key_client.post(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"name": "alice-key", "ttl": "30d"},
        )
        api_key_client.post(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"name": "bob-key", "ttl": "30d"},
        )
        resp = api_key_client.get("/auth/api-keys", headers={"Authorization": f"Bearer {token_a}"})
        names = [k["name"] for k in resp.json()]
        assert names == ["alice-key"]


class TestApiKeyRevoke:
    def test_revoke_success(self, api_key_client: TestClient) -> None:
        token = _login(api_key_client)
        created = api_key_client.post(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "x", "ttl": "30d"},
        ).json()
        resp = api_key_client.delete(
            f"/auth/api-keys/{created['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 204

        listed = api_key_client.get("/auth/api-keys", headers={"Authorization": f"Bearer {token}"}).json()
        assert listed[0]["revoked_at"] is not None
        assert listed[0]["is_active"] is False

    def test_revoke_is_idempotent(self, api_key_client: TestClient) -> None:
        token = _login(api_key_client)
        created = api_key_client.post(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "x", "ttl": "30d"},
        ).json()
        first = api_key_client.delete(
            f"/auth/api-keys/{created['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        second = api_key_client.delete(
            f"/auth/api-keys/{created['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert first.status_code == 204
        assert second.status_code == 204

    def test_revoke_other_users_key_returns_404(self, api_key_client: TestClient) -> None:
        token_a = _login(api_key_client, username="alice")
        token_b = _login(api_key_client, username="bob")
        created = api_key_client.post(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"name": "alice-key", "ttl": "30d"},
        ).json()
        resp = api_key_client.delete(
            f"/auth/api-keys/{created['id']}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404

    def test_revoke_unknown_key_returns_404(self, api_key_client: TestClient) -> None:
        token = _login(api_key_client)
        resp = api_key_client.delete(
            "/auth/api-keys/nonexistent",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_revoke_requires_jwt(self, api_key_client: TestClient) -> None:
        resp = api_key_client.delete("/auth/api-keys/anything")
        assert resp.status_code == 401
