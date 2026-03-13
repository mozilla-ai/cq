"""Tests for the CRAIC team API endpoints."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from team_api.app import app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("CRAIC_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CRAIC_JWT_SECRET", "test-secret")
    with TestClient(app) as c:
        yield c


def _propose_payload(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "domain": ["databases", "performance"],
        "insight": {
            "summary": "Use connection pooling",
            "detail": "Database connections are expensive to create.",
            "action": "Configure a connection pool with a max size of 10.",
        },
    }
    return {**defaults, **overrides}


def _approve_unit(client: TestClient, unit_id: str) -> None:
    """Approve a unit via the store for testing."""
    from team_api.app import _get_store

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
        assert body["domain"] == ["databases", "performance"]
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

    def test_propose_with_empty_domain_rejected(self, client: TestClient) -> None:
        payload = _propose_payload(domain=[])
        resp = client.post("/propose", json=payload)
        assert resp.status_code == 422

    def test_propose_with_whitespace_only_domains_rejected(
        self, client: TestClient
    ) -> None:
        payload = _propose_payload(domain=["  ", ""])
        resp = client.post("/propose", json=payload)
        assert resp.status_code == 422

    def test_propose_normalises_domains(self, client: TestClient) -> None:
        payload = _propose_payload(domain=["API", " Databases "])
        resp = client.post("/propose", json=payload)
        assert resp.status_code == 201
        assert resp.json()["domain"] == ["api", "databases"]


class TestQuery:
    def _insert_unit(self, client: TestClient, **overrides: Any) -> dict[str, Any]:
        resp = client.post("/propose", json=_propose_payload(**overrides))
        assert resp.status_code == 201
        body = resp.json()
        _approve_unit(client, body["id"])
        return body

    def test_query_returns_matching_units(self, client: TestClient) -> None:
        self._insert_unit(client, domain=["databases"])
        resp = client.get("/query", params={"domain": ["databases"]})
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["domain"] == ["databases"]

    def test_query_returns_empty_for_no_match(self, client: TestClient) -> None:
        self._insert_unit(client, domain=["databases"])
        resp = client.get("/query", params={"domain": ["networking"]})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_query_filters_by_language(self, client: TestClient) -> None:
        self._insert_unit(
            client,
            domain=["web"],
            context={"languages": ["python"], "frameworks": []},
        )
        self._insert_unit(
            client,
            domain=["web"],
            context={"languages": ["go"], "frameworks": []},
        )
        resp = client.get("/query", params={"domain": ["web"], "language": "python"})
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert "python" in results[0]["context"]["languages"]

    def test_query_respects_limit(self, client: TestClient) -> None:
        for _ in range(3):
            self._insert_unit(client, domain=["api"])
        resp = client.get("/query", params={"domain": ["api"], "limit": 2})
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_query_rejects_zero_limit(self, client: TestClient) -> None:
        resp = client.get("/query", params={"domain": ["api"], "limit": 0})
        assert resp.status_code == 422


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
        assert body["domains"] == {}

    def test_stats_after_inserts(self, client: TestClient) -> None:
        client.post("/propose", json=_propose_payload(domain=["api", "auth"]))
        client.post("/propose", json=_propose_payload(domain=["api", "payments"]))
        resp = client.get("/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_units"] == 2
        assert body["domains"]["api"] == 2
        assert body["domains"]["auth"] == 1
        assert body["domains"]["payments"] == 1


class TestReviewLifecycleEndToEnd:
    """End-to-end test covering propose -> review -> query -> stats lifecycle."""

    def test_full_review_lifecycle(self, client: TestClient) -> None:
        from team_api.app import _get_store
        from team_api.auth import hash_password

        store = _get_store()
        store.create_user("reviewer", hash_password("pass123"))

        # Log in.
        login_resp = client.post(
            "/auth/login",
            json={"username": "reviewer", "password": "pass123"},
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Agent proposes a KU.
        propose_resp = client.post(
            "/propose", json=_propose_payload(domain=["e2e-test"])
        )
        assert propose_resp.status_code == 201
        unit_id = propose_resp.json()["id"]

        # KU is not queryable yet (pending).
        query_resp = client.get("/query", params={"domain": ["e2e-test"]})
        assert len(query_resp.json()) == 0

        # KU appears in review queue.
        queue_resp = client.get("/review/queue", headers=headers)
        assert queue_resp.json()["total"] == 1

        # Reviewer approves the KU.
        approve_resp = client.post(f"/review/{unit_id}/approve", headers=headers)
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"

        # KU is now queryable.
        query_resp = client.get("/query", params={"domain": ["e2e-test"]})
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
            domain=["api", "payments"],
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
            params={"domain": ["api", "payments"], "language": "python"},
        )
        assert len(resp.json()) == 1
        assert resp.json()[0]["evidence"]["confidence"] == 0.5

        # Confirm boosts confidence.
        resp = client.post(f"/confirm/{unit_id}")
        assert resp.status_code == 200

        resp = client.get("/query", params={"domain": ["api", "payments"]})
        assert resp.json()[0]["evidence"]["confidence"] == pytest.approx(0.6)

        # Flag reduces confidence.
        resp = client.post(f"/flag/{unit_id}", json={"reason": "stale"})
        assert resp.status_code == 200

        resp = client.get("/query", params={"domain": ["api", "payments"]})
        result = resp.json()[0]
        assert result["evidence"]["confidence"] == pytest.approx(0.45)
        assert len(result["flags"]) == 1

        # Stats reflect the unit.
        resp = client.get("/stats")
        assert resp.json()["total_units"] == 1
