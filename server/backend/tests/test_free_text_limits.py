"""Tests that the server enforces the schema's free-text ceilings and stores them without truncation.

The ceilings live once, as ``maxLength`` / ``maxItems`` in ``schema/knowledge_unit.json``; the values here are read
from ``cq_schema`` rather than redeclared, so a schema change moves these tests with it.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import cq_schema
import pytest
from fastapi.testclient import TestClient

from cq_server.api.deps import require_api_key
from cq_server.app import app
from cq_server.migrations import run_migrations

from .db_helpers import sqlite_url

# Every ceiling that bounds a client-supplied free-text field on the propose path.
_LENGTH_CEILINGS = {
    "insight.summary": cq_schema.SUMMARY_MAX_LENGTH,
    "insight.detail": cq_schema.DETAIL_MAX_LENGTH,
    "insight.action": cq_schema.ACTION_MAX_LENGTH,
    "domains[]": cq_schema.DOMAIN_MAX_LENGTH,
    "created_by": cq_schema.CREATED_BY_MAX_LENGTH,
    "context.pattern": cq_schema.PATTERN_MAX_LENGTH,
    "context.languages[]": cq_schema.LANGUAGE_MAX_LENGTH,
    "context.frameworks[]": cq_schema.FRAMEWORK_MAX_LENGTH,
}


def _payload(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "domains": ["databases"],
        "insight": {"summary": "s", "detail": "d", "action": "a"},
    }
    return {**body, **overrides}


def _with_insight(field: str, value: str) -> dict[str, Any]:
    return _payload(insight={"summary": "s", "detail": "d", "action": "a", **{field: value}})


# Builders placing ``text`` in the field under test (domains are lower-cased, so "a" is used as filler).
_BUILDERS: dict[str, Callable[[str], dict[str, Any]]] = {
    "insight.summary": lambda text: _with_insight("summary", text),
    "insight.detail": lambda text: _with_insight("detail", text),
    "insight.action": lambda text: _with_insight("action", text),
    "domains[]": lambda text: _payload(domains=[text]),
    "context.pattern": lambda text: _payload(context={"pattern": text}),
    "context.languages[]": lambda text: _payload(context={"languages": [text]}),
    "context.frameworks[]": lambda text: _payload(context={"frameworks": [text]}),
}


def _make_client(username: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("CQ_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CQ_JWT_SECRET", "test-secret")
    monkeypatch.setenv("CQ_API_KEY_PEPPER", "test-pepper")
    app.dependency_overrides[require_api_key] = lambda: username
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(require_api_key, None)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from _make_client("test-user", tmp_path, monkeypatch)


@pytest.fixture()
def long_username_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from _make_client("u" * (cq_schema.CREATED_BY_MAX_LENGTH + 1), tmp_path, monkeypatch)


@pytest.mark.parametrize("field", sorted(_BUILDERS))
def test_propose_accepts_field_at_ceiling(client: TestClient, field: str) -> None:
    resp = client.post("/api/v1/knowledge", json=_BUILDERS[field]("a" * _LENGTH_CEILINGS[field]))
    assert resp.status_code == 201, resp.text


@pytest.mark.parametrize("field", sorted(_BUILDERS))
def test_propose_rejects_field_over_ceiling(client: TestClient, field: str) -> None:
    resp = client.post("/api/v1/knowledge", json=_BUILDERS[field]("a" * (_LENGTH_CEILINGS[field] + 1)))
    assert resp.status_code == 422, resp.text
    assert "at most" in resp.text


@pytest.mark.parametrize("field", sorted(_BUILDERS))
def test_propose_stores_field_at_ceiling_untruncated(client: TestClient, field: str) -> None:
    text = "a" * _LENGTH_CEILINGS[field]
    created = client.post("/api/v1/knowledge", json=_BUILDERS[field](text))
    assert created.status_code == 201, created.text
    assert text in created.text


def test_propose_rejects_too_many_domains(client: TestClient) -> None:
    domains = [f"d{i}" for i in range(cq_schema.DOMAINS_MAX_ITEMS + 1)]
    assert client.post("/api/v1/knowledge", json=_payload(domains=domains)).status_code == 422


def test_propose_rejects_too_many_languages_and_frameworks(client: TestClient) -> None:
    languages = [f"l{i}" for i in range(cq_schema.LANGUAGES_MAX_ITEMS + 1)]
    frameworks = [f"f{i}" for i in range(cq_schema.FRAMEWORKS_MAX_ITEMS + 1)]
    assert client.post("/api/v1/knowledge", json=_payload(context={"languages": languages})).status_code == 422
    assert client.post("/api/v1/knowledge", json=_payload(context={"frameworks": frameworks})).status_code == 422


def test_propose_rejects_username_over_created_by_ceiling(long_username_client: TestClient) -> None:
    """``created_by`` is the authenticated username, so an over-long one is rejected rather than truncated."""
    resp = long_username_client.post("/api/v1/knowledge", json=_payload())
    assert resp.status_code == 422, resp.text
    assert "created_by" in resp.text


_VARCHAR = re.compile(r"^(?:N?VARCHAR|N?CHAR|CHARACTER VARYING)\((\d+)\)$", re.IGNORECASE)


def test_storage_is_not_narrower_than_any_ceiling(tmp_path: Path) -> None:
    """No length-bounded column on the knowledge tables may be narrower than the widest ceiling it could hold.

    Free text is persisted inside the unbounded ``data`` document and the per-domain index, so the columns must
    be unbounded (``TEXT``) or at least as wide as the schema ceiling.
    """
    db = tmp_path / "guard.db"
    run_migrations(sqlite_url(db))
    conn = sqlite3.connect(str(db))
    try:
        holders = {
            ("knowledge_units", "data"): max(_LENGTH_CEILINGS.values()),
            ("knowledge_unit_domains", "domain"): cq_schema.DOMAIN_MAX_LENGTH,
        }
        for (table, column), ceiling in holders.items():
            declared = {row[1]: row[2] for row in conn.execute(f"PRAGMA table_info({table})")}[column]
            match = _VARCHAR.match(declared)
            assert match is None or int(match.group(1)) >= ceiling, f"{table}.{column} is {declared}, below {ceiling}"
    finally:
        conn.close()
