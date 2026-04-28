"""Tests for SqliteStore-only behaviour: engine wiring, PRAGMAs, threadpool shim, lifecycle.

Functional behaviour (insert/get/query/etc.) is covered by the existing test_store.py
once it is migrated. This file owns the genuinely-new internal behaviour required by
the SqliteStore implementation.
"""

import threading
from pathlib import Path

import pytest
from cq.models import Context, Insight, KnowledgeUnit, Tier, create_knowledge_unit

from cq_server.store import SqliteStore, Store


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "cq.db"


def _make_unit(domain: str = "auth") -> KnowledgeUnit:
    return create_knowledge_unit(
        domains=[domain],
        insight=Insight(summary="s", detail="d", action="a"),
        context=Context(),
        tier=Tier.PRIVATE,
        created_by="alice",
    )


async def test_sqlite_store_conforms_to_protocol(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        assert isinstance(store, Store)
    finally:
        await store.close()


async def test_close_is_idempotent(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    await store.close()
    await store.close()  # no raise


async def test_pragmas_applied_on_connect(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        with store._engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert conn.exec_driver_sql("PRAGMA journal_mode").scalar().lower() == "wal"
            assert conn.exec_driver_sql("PRAGMA synchronous").scalar() == 1  # NORMAL
            assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000
    finally:
        await store.close()


async def test_threadpool_shim_runs_off_event_loop(db_path: Path) -> None:
    """Sync work delegated to asyncio.to_thread must run in a worker thread,
    not block the event-loop thread."""
    store = SqliteStore(db_path=db_path)
    loop_thread_id = threading.get_ident()
    captured: dict[str, int] = {}

    def sync_probe() -> int:
        captured["thread_id"] = threading.get_ident()
        return 1

    try:
        # Use the same shim the real methods will use.
        result = await store._run_sync(sync_probe)
        assert result == 1
        assert captured["thread_id"] != loop_thread_id
    finally:
        await store.close()


async def test_schema_present_after_construct(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        with store._engine.connect() as conn:
            tables = {row[0] for row in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}
            assert {"knowledge_units", "knowledge_unit_domains", "users", "api_keys"} <= tables
    finally:
        await store.close()


async def test_insert_get_any_roundtrip(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        unit = _make_unit()
        await store.insert(unit)
        retrieved = await store.get_any(unit.id)
        assert retrieved == unit
        # get() filters by approved status — should be None pre-approval.
        assert await store.get(unit.id) is None
    finally:
        await store.close()


async def test_update_and_review_roundtrip(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        unit = _make_unit()
        await store.insert(unit)
        await store.set_review_status(unit.id, "approved", "bob")
        status = await store.get_review_status(unit.id)
        assert status == {"status": "approved", "reviewed_by": "bob", "reviewed_at": status["reviewed_at"]}
        # update preserves id; replace summary
        unit2 = unit.model_copy(update={"insight": Insight(summary="new", detail="d", action="a")})
        await store.update(unit2)
        retrieved = await store.get_any(unit.id)
        assert retrieved.insight.summary == "new"
    finally:
        await store.close()


async def test_query_filters_and_ranks(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        a = _make_unit("auth")
        b = _make_unit("auth")
        await store.insert(a)
        await store.insert(b)
        await store.set_review_status(a.id, "approved", "r")
        await store.set_review_status(b.id, "approved", "r")
        results = await store.query(["auth"])
        assert {u.id for u in results} == {a.id, b.id}
    finally:
        await store.close()


async def test_count_and_domain_counts(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        u = _make_unit("auth")
        await store.insert(u)
        await store.set_review_status(u.id, "approved", "r")
        assert await store.count() == 1
        assert await store.domain_counts() == {"auth": 1}
        assert await store.counts_by_status() == {"approved": 1}
        assert await store.counts_by_tier() == {"private": 1}
    finally:
        await store.close()
