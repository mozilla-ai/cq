"""Tests for SqliteStore-only behaviour: engine wiring, PRAGMAs, threadpool shim, lifecycle.

Functional behaviour (insert/get/query/etc.) is covered by the existing test_store.py
once it is migrated. This file owns the genuinely-new internal behaviour required by
the SqliteStore implementation.
"""

import threading
from pathlib import Path

import pytest

from cq_server.store import SqliteStore, Store


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "cq.db"


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
