"""End-to-end smoke for the cq server against a temporary SQLite database.

Required by the Definition of Done in #308: the server boots, accepts a
write, and serves a read through the public API surface. The write is
seeded directly via the knowledge repository (bypassing the api-key flow)
so this test stays focused on the boot + Database + route-layer integration.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cq_server.app import app


def test_e2e_propose_via_store_query_via_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "smoke.db"
    monkeypatch.setenv("CQ_DB_PATH", str(db))
    monkeypatch.setenv("CQ_JWT_SECRET", "smoke-jwt-secret-bytes")
    monkeypatch.setenv("CQ_API_KEY_PEPPER", "smoke-pepper-bytes")

    with TestClient(app) as client:
        from cq.models import Context, Insight, Tier, create_knowledge_unit

        from cq_server.repositories import KnowledgeRepository, ReviewRepository

        knowledge = KnowledgeRepository(client.app.state.database)
        reviews = ReviewRepository(client.app.state.database)
        unit = create_knowledge_unit(
            domains=["smoke"],
            insight=Insight(summary="s", detail="d", action="a"),
            context=Context(),
            tier=Tier.PRIVATE,
            created_by="smoke",
        )
        asyncio.run(knowledge.insert(unit))
        asyncio.run(reviews.set_status(unit.id, "approved", "smoke-reviewer"))

        resp = client.get("/api/v1/knowledge", params={"domains": "smoke"})
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.json()["data"]]
        assert unit.id in ids

    assert db.exists()
