"""Tests for SqliteStore-only behaviour: engine wiring, PRAGMAs, threadpool shim, lifecycle.

Functional behaviour (insert/get/query/etc.) is covered by the existing test_store.py
once it is migrated. This file owns the genuinely-new internal behaviour required by
the SqliteStore implementation.
"""

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
