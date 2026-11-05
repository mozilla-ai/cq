"""Tests that the server enforces the schema's free-text ceilings and stores them without truncation.

The ceilings live once, as ``maxLength`` / ``maxItems`` in ``schema/knowledge_unit.json``; the values here are read
from ``cq_schema`` rather than redeclared, so a schema change moves these tests with it.
"""

from __future__ import annotations

import json
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


_CEILING_USERNAME = "u" * cq_schema.CREATED_BY_MAX_LENGTH


def _fetch(tmp_path: Path, sql: str, *params: object) -> list[tuple[Any, ...]]:
    """Read rows straight from the test database, which the response body cannot speak for."""
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _field_name(field: str) -> str:
    """Return the bare field name the validation message cites, e.g. ``context.languages[]`` -> ``languages``."""
    return field.rsplit(".", 1)[-1].removesuffix("[]")


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
    # CQ_DATABASE_URL outranks CQ_DB_PATH, so an inherited one would send the app to another database.
    monkeypatch.delenv("CQ_DATABASE_URL", raising=False)
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
def ceiling_username_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from _make_client(_CEILING_USERNAME, tmp_path, monkeypatch)


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
    ceiling = _LENGTH_CEILINGS[field]
    resp = client.post("/api/v1/knowledge", json=_BUILDERS[field]("a" * (ceiling + 1)))
    assert resp.status_code == 422, resp.text
    # The message names the offending field and its ceiling, so another field's limit cannot satisfy this case.
    assert f"{_field_name(field)} must be at most {ceiling} characters" in resp.text


@pytest.mark.parametrize("field", sorted(_BUILDERS))
def test_propose_stores_field_at_ceiling_untruncated(client: TestClient, tmp_path: Path, field: str) -> None:
    """Read the persisted row back: the response is built from the in-memory unit and cannot see a lossy write."""
    text = "a" * _LENGTH_CEILINGS[field]
    created = client.post("/api/v1/knowledge", json=_BUILDERS[field](text))
    assert created.status_code == 201, created.text
    rows = _fetch(tmp_path, "SELECT data FROM knowledge_units WHERE id = ?", created.json()["id"])
    assert rows
    assert text in rows[0][0]


def test_propose_stores_domain_index_at_ceiling_untruncated(client: TestClient, tmp_path: Path) -> None:
    """Domain lookup reads the per-domain index rather than ``data``, so the index needs its own assertion."""
    domain = "a" * cq_schema.DOMAIN_MAX_LENGTH
    created = client.post("/api/v1/knowledge", json=_payload(domains=[domain]))
    assert created.status_code == 201, created.text
    rows = _fetch(tmp_path, "SELECT domain FROM knowledge_unit_domains WHERE unit_id = ?", created.json()["id"])
    assert [row[0] for row in rows] == [domain]


def test_propose_stores_maximal_unit_untruncated(client: TestClient, tmp_path: Path) -> None:
    """A unit at every ceiling at once round-trips through storage intact, since ``data`` holds the whole document."""
    body = _payload(
        domains=["a" * cq_schema.DOMAIN_MAX_LENGTH],
        insight={
            "summary": "s" * cq_schema.SUMMARY_MAX_LENGTH,
            "detail": "d" * cq_schema.DETAIL_MAX_LENGTH,
            "action": "a" * cq_schema.ACTION_MAX_LENGTH,
        },
        context={
            "pattern": "p" * cq_schema.PATTERN_MAX_LENGTH,
            "languages": ["l" * cq_schema.LANGUAGE_MAX_LENGTH],
            "frameworks": ["f" * cq_schema.FRAMEWORK_MAX_LENGTH],
        },
    )
    created = client.post("/api/v1/knowledge", json=body)
    assert created.status_code == 201, created.text
    rows = _fetch(tmp_path, "SELECT data FROM knowledge_units WHERE id = ?", created.json()["id"])
    assert rows
    stored = json.loads(rows[0][0])
    assert stored["insight"] == body["insight"]
    assert stored["context"]["pattern"] == body["context"]["pattern"]
    assert stored["context"]["languages"] == body["context"]["languages"]
    assert stored["context"]["frameworks"] == body["context"]["frameworks"]
    assert stored["domains"] == body["domains"]


# One entry per item-count ceiling, so a regression in one cap does not hide the state of another.
_ITEM_CEILINGS: dict[str, tuple[int, Callable[[list[str]], dict[str, Any]]]] = {
    "domains": (cq_schema.DOMAINS_MAX_ITEMS, lambda items: _payload(domains=items)),
    "context.languages": (cq_schema.LANGUAGES_MAX_ITEMS, lambda items: _payload(context={"languages": items})),
    "context.frameworks": (cq_schema.FRAMEWORKS_MAX_ITEMS, lambda items: _payload(context={"frameworks": items})),
}


@pytest.mark.parametrize("field", sorted(_ITEM_CEILINGS))
def test_propose_accepts_item_count_at_ceiling(client: TestClient, field: str) -> None:
    ceiling, build = _ITEM_CEILINGS[field]
    resp = client.post("/api/v1/knowledge", json=build([f"i{n}" for n in range(ceiling)]))
    assert resp.status_code == 201, resp.text


@pytest.mark.parametrize("field", sorted(_ITEM_CEILINGS))
def test_propose_rejects_item_count_over_ceiling(client: TestClient, field: str) -> None:
    ceiling, build = _ITEM_CEILINGS[field]
    resp = client.post("/api/v1/knowledge", json=build([f"i{n}" for n in range(ceiling + 1)]))
    assert resp.status_code == 422, resp.text


def test_propose_accepts_username_at_created_by_ceiling(ceiling_username_client: TestClient, tmp_path: Path) -> None:
    """``created_by`` is the authenticated username, so one exactly at the ceiling must survive the write."""
    created = ceiling_username_client.post("/api/v1/knowledge", json=_payload())
    assert created.status_code == 201, created.text
    rows = _fetch(tmp_path, "SELECT data FROM knowledge_units WHERE id = ?", created.json()["id"])
    assert rows
    assert json.loads(rows[0][0])["created_by"] == _CEILING_USERNAME


def test_propose_rejects_username_over_created_by_ceiling(long_username_client: TestClient) -> None:
    """``created_by`` is the authenticated username, so an over-long one is rejected rather than truncated."""
    resp = long_username_client.post("/api/v1/knowledge", json=_payload())
    assert resp.status_code == 422, resp.text
    assert "created_by" in resp.text


# Free text is persisted inside the ``data`` document (the whole serialised unit, so its width is the sum of every
# bounded field, not the largest one) and, for domains, in the per-domain index. Declaring these unbounded is the
# invariant that keeps storage at or above every ceiling; a narrower ``VARCHAR`` must fail here.
_UNBOUNDED_COLUMNS = (("knowledge_units", "data"), ("knowledge_unit_domains", "domain"))


@pytest.mark.parametrize(("table", "column"), _UNBOUNDED_COLUMNS)
def test_storage_column_is_unbounded(tmp_path: Path, table: str, column: str) -> None:
    db = tmp_path / "guard.db"
    run_migrations(sqlite_url(db))
    conn = sqlite3.connect(str(db))
    try:
        declared = {row[1]: row[2] for row in conn.execute(f"PRAGMA table_info({table})")}[column]
    finally:
        conn.close()
    assert declared.upper() == "TEXT", f"{table}.{column} is {declared}; a bounded column risks truncating a unit"
