"""Tests for the cq remote API endpoints."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from cq_server.app import app
from cq_server.deps import require_api_key

TEST_USERNAME = "test-user"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("CQ_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CQ_JWT_SECRET", "test-secret")
    monkeypatch.setenv("CQ_API_KEY_PEPPER", "test-pepper")
    app.dependency_overrides[require_api_key] = lambda: TEST_USERNAME
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(require_api_key, None)


@pytest.fixture()
def enforced_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """TestClient with real API key enforcement (no dep override)."""
    monkeypatch.setenv("CQ_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CQ_JWT_SECRET", "test-secret")
    monkeypatch.setenv("CQ_API_KEY_PEPPER", "test-pepper")
    app.dependency_overrides.pop(require_api_key, None)
    with TestClient(app) as c:
        yield c


def _seed_user_and_login(
    client: TestClient,
    username: str = "alice",
    password: str = "secret123",
) -> str:
    from cq_server.app import _get_store
    from cq_server.auth import hash_password

    _get_store().create_user(username, hash_password(password))
    resp = client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["token"]


def _create_api_key_plaintext(client: TestClient, jwt_token: str, name: str = "test") -> str:
    resp = client.post(
        "/auth/api-keys",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"name": name, "ttl": "30d"},
    )
    assert resp.status_code == 201
    return resp.json()["token"]


def _propose_payload(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "domains": ["databases", "performance"],
        "insight": {
            "summary": "Use connection pooling",
            "detail": "Database connections are expensive to create.",
            "action": "Configure a connection pool with a max size of 10.",
        },
    }
    return {**defaults, **overrides}


def _approve_unit(client: TestClient, unit_id: str) -> None:
    """Approve a unit via the store for testing."""
    from cq_server.app import _get_store

    store = _get_store()
    store.set_review_status(unit_id, "approved", "test-reviewer")


class TestHealth:
    def test_health_returns_ok(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestPropose:
    def test_propose_creates_unit(self, client: TestClient) -> None:
        resp = client.post("/propose", json=_propose_payload())
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"].startswith("ku_")
        assert body["domains"] == ["databases", "performance"]
        assert body["insight"]["summary"] == "Use connection pooling"
        assert body["evidence"]["confidence"] == 0.5

    def test_propose_with_context(self, client: TestClient) -> None:
        payload = _propose_payload(
            context={"languages": ["python"], "frameworks": ["fastapi"]},
        )
        resp = client.post("/propose", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert "python" in body["context"]["languages"]
        assert "fastapi" in body["context"]["frameworks"]

    def test_propose_with_empty_domains_rejected(self, client: TestClient) -> None:
        payload = _propose_payload(domains=[])
        resp = client.post("/propose", json=payload)
        assert resp.status_code == 422

    def test_propose_with_whitespace_only_domains_rejected(self, client: TestClient) -> None:
        payload = _propose_payload(domains=["  ", ""])
        resp = client.post("/propose", json=payload)
        assert resp.status_code == 422

    def test_propose_normalizes_domains(self, client: TestClient) -> None:
        payload = _propose_payload(domains=["API", " Databases "])
        resp = client.post("/propose", json=payload)
        assert resp.status_code == 201
        assert resp.json()["domains"] == ["api", "databases"]


class TestQuery:
    def _insert_unit(self, client: TestClient, **overrides: Any) -> dict[str, Any]:
        resp = client.post("/propose", json=_propose_payload(**overrides))
        assert resp.status_code == 201
        body = resp.json()
        _approve_unit(client, body["id"])
        return body

    def test_query_returns_matching_units(self, client: TestClient) -> None:
        self._insert_unit(client, domains=["databases"])
        resp = client.get("/query", params={"domains": ["databases"]})
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["domains"] == ["databases"]

    def test_query_returns_empty_for_no_match(self, client: TestClient) -> None:
        self._insert_unit(client, domains=["databases"])
        resp = client.get("/query", params={"domains": ["networking"]})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_query_boosts_matching_language(self, client: TestClient) -> None:
        self._insert_unit(
            client,
            domains=["web"],
            context={"languages": ["python"], "frameworks": []},
        )
        self._insert_unit(
            client,
            domains=["web"],
            context={"languages": ["go"], "frameworks": []},
        )
        resp = client.get("/query", params={"domains": ["web"], "languages": ["python"]})
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 2
        assert "python" in results[0]["context"]["languages"]

    def test_query_boosts_any_matching_language(self, client: TestClient) -> None:
        self._insert_unit(
            client,
            domains=["web"],
            context={"languages": ["python"], "frameworks": []},
        )
        self._insert_unit(
            client,
            domains=["web"],
            context={"languages": ["go"], "frameworks": []},
        )
        self._insert_unit(
            client,
            domains=["web"],
            context={"languages": ["rust"], "frameworks": []},
        )
        resp = client.get(
            "/query",
            params={"domains": ["web"], "languages": ["python", "go"]},
        )
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 3
        top_langs = {results[0]["context"]["languages"][0], results[1]["context"]["languages"][0]}
        assert top_langs == {"python", "go"}

    def test_query_respects_limit(self, client: TestClient) -> None:
        for _ in range(3):
            self._insert_unit(client, domains=["api"])
        resp = client.get("/query", params={"domains": ["api"], "limit": 2})
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_query_rejects_zero_limit(self, client: TestClient) -> None:
        resp = client.get("/query", params={"domains": ["api"], "limit": 0})
        assert resp.status_code == 422

    def test_query_boosts_matching_pattern(self, client: TestClient) -> None:
        self._insert_unit(
            client,
            domains=["api"],
            context={"languages": [], "frameworks": [], "pattern": "api-client"},
        )
        self._insert_unit(
            client,
            domains=["api"],
            context={"languages": [], "frameworks": [], "pattern": "other-pattern"},
        )
        resp = client.get("/query", params={"domains": ["api"], "pattern": "api-client"})
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 2
        assert results[0]["context"]["pattern"] == "api-client"


class TestConfirm:
    def test_confirm_boosts_confidence(self, client: TestClient) -> None:
        created = client.post("/propose", json=_propose_payload()).json()
        _approve_unit(client, created["id"])
        resp = client.post(f"/confirm/{created['id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["evidence"]["confirmations"] == 2
        assert body["evidence"]["confidence"] > 0.5

    def test_confirm_pending_unit_returns_404(self, client: TestClient) -> None:
        created = client.post("/propose", json=_propose_payload()).json()
        resp = client.post(f"/confirm/{created['id']}")
        assert resp.status_code == 404

    def test_confirm_missing_unit_returns_404(self, client: TestClient) -> None:
        resp = client.post("/confirm/ku_nonexistent")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


class TestFlag:
    def test_flag_reduces_confidence(self, client: TestClient) -> None:
        created = client.post("/propose", json=_propose_payload()).json()
        _approve_unit(client, created["id"])
        resp = client.post(f"/flag/{created['id']}", json={"reason": "stale"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["evidence"]["confidence"] < 0.5
        assert len(body["flags"]) == 1

    def test_flag_pending_unit_returns_404(self, client: TestClient) -> None:
        created = client.post("/propose", json=_propose_payload()).json()
        resp = client.post(f"/flag/{created['id']}", json={"reason": "stale"})
        assert resp.status_code == 404

    def test_flag_missing_unit_returns_404(self, client: TestClient) -> None:
        resp = client.post("/flag/ku_nonexistent", json={"reason": "stale"})
        assert resp.status_code == 404

    def test_flag_with_invalid_reason_rejected(self, client: TestClient) -> None:
        created = client.post("/propose", json=_propose_payload()).json()
        resp = client.post(f"/flag/{created['id']}", json={"reason": "invalid_reason"})
        assert resp.status_code == 422


class TestStats:
    def test_stats_empty_store(self, client: TestClient) -> None:
        resp = client.get("/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_units"] == 0
        assert body["tiers"] == {}
        assert body["domains"] == {}

    def test_stats_after_inserts(self, client: TestClient) -> None:
        from cq_server.app import _get_store

        r1 = client.post("/propose", json=_propose_payload(domains=["api", "auth"]))
        r2 = client.post("/propose", json=_propose_payload(domains=["api", "payments"]))
        store = _get_store()
        store.set_review_status(r1.json()["id"], "approved", "tester")
        store.set_review_status(r2.json()["id"], "approved", "tester")
        resp = client.get("/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_units"] == 2
        assert body["tiers"] == {"private": 2}
        assert body["domains"]["api"] == 2
        assert body["domains"]["auth"] == 1
        assert body["domains"]["payments"] == 1


class TestReviewLifecycleEndToEnd:
    """End-to-end test covering propose -> review -> query -> stats lifecycle."""

    def test_full_review_lifecycle(self, client: TestClient) -> None:
        from cq_server.app import _get_store
        from cq_server.auth import hash_password

        store = _get_store()
        store.create_user("reviewer", hash_password("pass123"))

        # Log in.
        login_resp = client.post(
            "/auth/login",
            json={
                "username": "reviewer",
                "password": "pass123",  # pragma: allowlist secret
            },
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Agent proposes a KU.
        propose_resp = client.post("/propose", json=_propose_payload(domains=["e2e-test"]))
        assert propose_resp.status_code == 201
        unit_id = propose_resp.json()["id"]

        # KU is not queryable yet (pending).
        query_resp = client.get("/query", params={"domains": ["e2e-test"]})
        assert len(query_resp.json()) == 0

        # KU appears in review queue.
        queue_resp = client.get("/review/queue", headers=headers)
        assert queue_resp.json()["total"] == 1

        # Reviewer approves the KU.
        approve_resp = client.post(f"/review/{unit_id}/approve", headers=headers)
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"

        # KU is now queryable.
        query_resp = client.get("/query", params={"domains": ["e2e-test"]})
        assert len(query_resp.json()) == 1

        # Queue is empty.
        queue_resp = client.get("/review/queue", headers=headers)
        assert queue_resp.json()["total"] == 0

        # Agent can confirm the approved KU.
        confirm_resp = client.post(f"/confirm/{unit_id}")
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["evidence"]["confirmations"] == 2

        # Stats reflect the state including trends.
        stats_resp = client.get("/review/stats", headers=headers)
        body = stats_resp.json()
        assert body["counts"]["approved"] == 1
        assert "trends" in body
        assert "daily" in body["trends"]


class TestEndToEnd:
    def test_propose_confirm_flag_lifecycle(self, client: TestClient) -> None:
        # Propose a unit.
        payload = _propose_payload(
            domains=["api", "payments"],
            context={"languages": ["python"], "frameworks": ["fastapi"]},
        )
        created = client.post("/propose", json=payload)
        assert created.status_code == 201
        unit_id = created.json()["id"]

        # Approve the unit so it becomes queryable.
        _approve_unit(client, unit_id)

        # Query returns the unit.
        resp = client.get(
            "/query",
            params={"domains": ["api", "payments"], "languages": ["python"]},
        )
        assert len(resp.json()) == 1
        assert resp.json()[0]["evidence"]["confidence"] == 0.5

        # Confirm boosts confidence.
        resp = client.post(f"/confirm/{unit_id}")
        assert resp.status_code == 200

        resp = client.get("/query", params={"domains": ["api", "payments"]})
        assert resp.json()[0]["evidence"]["confidence"] == pytest.approx(0.6)

        # Flag reduces confidence.
        resp = client.post(f"/flag/{unit_id}", json={"reason": "stale"})
        assert resp.status_code == 200

        resp = client.get("/query", params={"domains": ["api", "payments"]})
        result = resp.json()[0]
        assert result["evidence"]["confidence"] == pytest.approx(0.45)
        assert len(result["flags"]) == 1

        # Stats reflect the unit.
        resp = client.get("/stats")
        assert resp.json()["total_units"] == 1


class TestApiKeyEnforcement:
    def test_propose_without_key_is_rejected(self, enforced_client: TestClient) -> None:
        resp = enforced_client.post("/propose", json=_propose_payload())
        assert resp.status_code == 401

    def test_propose_with_wrong_prefix_is_rejected(self, enforced_client: TestClient) -> None:
        resp = enforced_client.post(
            "/propose",
            json=_propose_payload(),
            headers={"Authorization": "Bearer sk-something"},
        )
        assert resp.status_code == 401

    def test_propose_with_unknown_key_is_rejected(self, enforced_client: TestClient) -> None:
        resp = enforced_client.post(
            "/propose",
            json=_propose_payload(),
            headers={"Authorization": "Bearer cqa_unknownkey"},
        )
        assert resp.status_code == 401

    def test_propose_with_valid_key_succeeds(self, enforced_client: TestClient) -> None:
        jwt_token = _seed_user_and_login(enforced_client)
        api_token = _create_api_key_plaintext(enforced_client, jwt_token)
        resp = enforced_client.post(
            "/propose",
            json=_propose_payload(),
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert resp.status_code == 201

    def test_propose_overrides_created_by(self, enforced_client: TestClient) -> None:
        jwt_token = _seed_user_and_login(enforced_client, username="alice")
        api_token = _create_api_key_plaintext(enforced_client, jwt_token)
        payload = _propose_payload()
        payload["created_by"] = "impostor"
        resp = enforced_client.post(
            "/propose",
            json=payload,
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["created_by"] == "alice"

    def test_propose_with_revoked_key_is_rejected(self, enforced_client: TestClient) -> None:
        jwt_token = _seed_user_and_login(enforced_client)
        create_resp = enforced_client.post(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {jwt_token}"},
            json={"name": "revokeable", "ttl": "30d"},
        )
        body = create_resp.json()
        api_token = body["token"]
        enforced_client.delete(
            f"/auth/api-keys/{body['id']}",
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        resp = enforced_client.post(
            "/propose",
            json=_propose_payload(),
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert resp.status_code == 401

    def test_query_stays_open_under_enforcement(self, enforced_client: TestClient) -> None:
        resp = enforced_client.get("/query", params={"domains": ["anything"]})
        assert resp.status_code == 200

    def test_stats_stays_open_under_enforcement(self, enforced_client: TestClient) -> None:
        resp = enforced_client.get("/stats")
        assert resp.status_code == 200

    def test_health_stays_open_under_enforcement(self, enforced_client: TestClient) -> None:
        resp = enforced_client.get("/health")
        assert resp.status_code == 200

    def test_last_used_at_updates_after_request(self, enforced_client: TestClient) -> None:
        jwt_token = _seed_user_and_login(enforced_client)
        create = enforced_client.post(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {jwt_token}"},
            json={"name": "trace", "ttl": "30d"},
        ).json()
        api_token = create["token"]
        listed = enforced_client.get(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {jwt_token}"},
        ).json()
        assert listed[0]["last_used_at"] is None

        enforced_client.post(
            "/propose",
            json=_propose_payload(),
            headers={"Authorization": f"Bearer {api_token}"},
        )

        listed_after = enforced_client.get(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {jwt_token}"},
        ).json()
        assert listed_after[0]["last_used_at"] is not None

    def test_confirm_and_flag_require_api_key(self, enforced_client: TestClient) -> None:
        jwt_token = _seed_user_and_login(enforced_client)
        api_token = _create_api_key_plaintext(enforced_client, jwt_token)
        propose_resp = enforced_client.post(
            "/propose",
            json=_propose_payload(),
            headers={"Authorization": f"Bearer {api_token}"},
        )
        unit_id = propose_resp.json()["id"]
        _approve_unit(enforced_client, unit_id)

        # Without key both are rejected.
        assert enforced_client.post(f"/confirm/{unit_id}").status_code == 401
        assert enforced_client.post(f"/flag/{unit_id}", json={"reason": "stale"}).status_code == 401

        # With key both succeed.
        headers = {"Authorization": f"Bearer {api_token}"}
        assert enforced_client.post(f"/confirm/{unit_id}", headers=headers).status_code == 200
        assert enforced_client.post(f"/flag/{unit_id}", json={"reason": "stale"}, headers=headers).status_code == 200
