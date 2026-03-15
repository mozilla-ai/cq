"""Tests for the review endpoints."""

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


def _login(
    client: TestClient, username: str = "reviewer", password: str = "pass123"
) -> str:
    """Seed a user, log in, return the JWT token."""
    from team_api.app import _get_store
    from team_api.auth import hash_password

    store = _get_store()
    try:
        store.create_user(username, hash_password(password))
    except Exception:
        pass
    resp = client.post("/auth/login", json={"username": username, "password": password})
    return resp.json()["token"]


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _propose(client: TestClient, **overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "domain": ["api", "testing"],
        "insight": {
            "summary": "Test insight",
            "detail": "Detail here.",
            "action": "Do the thing.",
        },
    }
    resp = client.post("/propose", json={**defaults, **overrides})
    assert resp.status_code == 201
    return resp.json()


class TestReviewQueue:
    def test_queue_returns_pending(self, client: TestClient) -> None:
        token = _login(client)
        _propose(client)
        resp = client.get("/review/queue", headers=_auth_header(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["status"] == "pending"

    def test_queue_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/review/queue")
        assert resp.status_code == 401

    def test_queue_empty(self, client: TestClient) -> None:
        token = _login(client)
        resp = client.get("/review/queue", headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestApprove:
    def test_approve_pending_unit(self, client: TestClient) -> None:
        token = _login(client)
        unit = _propose(client)
        resp = client.post(f"/review/{unit['id']}/approve", headers=_auth_header(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "approved"
        assert body["reviewed_by"] == "reviewer"

    def test_approve_already_reviewed_returns_409(self, client: TestClient) -> None:
        token = _login(client)
        unit = _propose(client)
        client.post(f"/review/{unit['id']}/approve", headers=_auth_header(token))
        resp = client.post(f"/review/{unit['id']}/approve", headers=_auth_header(token))
        assert resp.status_code == 409

    def test_approve_nonexistent_returns_404(self, client: TestClient) -> None:
        token = _login(client)
        resp = client.post(
            "/review/ku_nonexistent/approve", headers=_auth_header(token)
        )
        assert resp.status_code == 404

    def test_approved_unit_appears_in_query(self, client: TestClient) -> None:
        token = _login(client)
        unit = _propose(client, domain=["searchable"])
        client.post(f"/review/{unit['id']}/approve", headers=_auth_header(token))
        resp = client.get("/query", params={"domain": ["searchable"]})
        assert len(resp.json()) == 1


class TestReject:
    def test_reject_pending_unit(self, client: TestClient) -> None:
        token = _login(client)
        unit = _propose(client)
        resp = client.post(f"/review/{unit['id']}/reject", headers=_auth_header(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "rejected"

    def test_rejected_unit_not_in_query(self, client: TestClient) -> None:
        token = _login(client)
        unit = _propose(client, domain=["hidden"])
        client.post(f"/review/{unit['id']}/reject", headers=_auth_header(token))
        resp = client.get("/query", params={"domain": ["hidden"]})
        assert len(resp.json()) == 0


class TestReviewStats:
    def test_stats_counts(self, client: TestClient) -> None:
        token = _login(client)
        u1 = _propose(client)
        u2 = _propose(client)
        _propose(client)
        client.post(f"/review/{u1['id']}/approve", headers=_auth_header(token))
        client.post(f"/review/{u2['id']}/reject", headers=_auth_header(token))
        resp = client.get("/review/stats", headers=_auth_header(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["counts"]["approved"] == 1
        assert body["counts"]["rejected"] == 1
        assert body["counts"]["pending"] == 1


class TestReviewStatsDetail:
    def test_stats_includes_confidence_distribution(self, client: TestClient) -> None:
        token = _login(client)
        unit = _propose(client)
        client.post(f"/review/{unit['id']}/approve", headers=_auth_header(token))
        resp = client.get("/review/stats", headers=_auth_header(token))
        body = resp.json()
        assert "confidence_distribution" in body
        total = sum(body["confidence_distribution"].values())
        assert total == 1

    def test_stats_includes_recent_activity(self, client: TestClient) -> None:
        token = _login(client)
        unit = _propose(client)
        client.post(f"/review/{unit['id']}/approve", headers=_auth_header(token))
        resp = client.get("/review/stats", headers=_auth_header(token))
        body = resp.json()
        assert len(body["recent_activity"]) >= 1

    def test_activity_shows_terminal_state_only(self, client: TestClient) -> None:
        """A reviewed KU should appear once (as approved/rejected), not twice."""
        token = _login(client)
        unit = _propose(client)
        client.post(f"/review/{unit['id']}/approve", headers=_auth_header(token))
        resp = client.get("/review/stats", headers=_auth_header(token))
        events = resp.json()["recent_activity"]
        unit_events = [e for e in events if e["unit_id"] == unit["id"]]
        assert len(unit_events) == 1
        assert unit_events[0]["type"] == "approved"

    def test_activity_shows_proposed_for_pending(self, client: TestClient) -> None:
        """A pending KU should appear as proposed."""
        token = _login(client)
        unit = _propose(client)
        resp = client.get("/review/stats", headers=_auth_header(token))
        events = resp.json()["recent_activity"]
        unit_events = [e for e in events if e["unit_id"] == unit["id"]]
        assert len(unit_events) == 1
        assert unit_events[0]["type"] == "proposed"
