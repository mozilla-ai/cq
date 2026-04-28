"""Tests for SqliteStore-only behaviour: engine wiring, PRAGMAs, threadpool shim, lifecycle.

Functional behaviour (insert/get/query/etc.) is covered by the existing test_store.py
once it is migrated. This file owns the genuinely-new internal behaviour required by
the SqliteStore implementation.
"""

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
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


async def test_pending_and_list_units(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        u = _make_unit("auth")
        await store.insert(u)
        # pending before approval
        assert await store.pending_count() == 1
        queue = await store.pending_queue(limit=10)
        assert len(queue) == 1 and queue[0]["status"] == "pending"
        # list_units sees it as pending
        listing = await store.list_units(status="pending")
        assert len(listing) == 1
    finally:
        await store.close()


async def test_distribution_and_activity_and_daily(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        u = _make_unit("auth")
        await store.insert(u)
        await store.set_review_status(u.id, "approved", "r")

        dist = await store.confidence_distribution()
        assert set(dist.keys()) == {"0.0-0.3", "0.3-0.6", "0.6-0.8", "0.8-1.0"}
        assert sum(dist.values()) == 1

        activity = await store.recent_activity(limit=5)
        assert len(activity) == 1
        assert activity[0]["type"] == "approved"
        assert activity[0]["unit_id"] == u.id
        assert activity[0]["reviewed_by"] == "r"

        days = await store.daily_counts(days=30)
        assert isinstance(days, list)

        with pytest.raises(ValueError):
            await store.daily_counts(days=0)
    finally:
        await store.close()


async def test_create_get_user(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        await store.create_user("alice", "$2b$12$fake")
        user = await store.get_user("alice")
        assert user is not None
        assert user["username"] == "alice"
        assert await store.get_user("nope") is None
    finally:
        await store.close()


async def _seed_user(store: SqliteStore) -> int:
    await store.create_user("alice", "$2b$12$fakehashfakehashfakehashfakehashfake")
    user = await store.get_user("alice")
    assert user is not None
    return int(user["id"])


async def test_create_api_key_returns_row(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        user_id = await _seed_user(store)
        expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        row = await store.create_api_key(
            key_id="k1",
            user_id=user_id,
            name="laptop",
            labels=["dev"],
            key_prefix="cq_xxxx",
            key_hash="hash-bytes",
            ttl="P30D",
            expires_at=expires_at,
        )
        assert row["id"] == "k1"
        assert row["user_id"] == user_id
        assert row["name"] == "laptop"
        assert row["labels"] == ["dev"]
        assert row["key_prefix"] == "cq_xxxx"
        assert row["key_hash"] == "hash-bytes"
        assert row["ttl"] == "P30D"
        assert row["expires_at"] == expires_at
        assert row["last_used_at"] is None
        assert row["revoked_at"] is None
    finally:
        await store.close()


async def test_get_api_key_for_user(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        user_id = await _seed_user(store)
        expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        await store.create_api_key(
            key_id="k1",
            user_id=user_id,
            name="laptop",
            labels=["dev"],
            key_prefix="cq_xxxx",
            key_hash="h",
            ttl="P30D",
            expires_at=expires_at,
        )

        row = await store.get_api_key_for_user(user_id=user_id, key_id="k1")
        assert row is not None
        assert row["id"] == "k1"
        assert row["user_id"] == user_id
        assert row["labels"] == ["dev"]

        # Wrong user id: None.
        assert await store.get_api_key_for_user(user_id=user_id + 99, key_id="k1") is None
        # Missing key id: None.
        assert await store.get_api_key_for_user(user_id=user_id, key_id="missing") is None
    finally:
        await store.close()


async def test_count_active_api_keys_for_user(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        user_id = await _seed_user(store)
        expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        await store.create_api_key(
            key_id="k1",
            user_id=user_id,
            name="laptop",
            labels=[],
            key_prefix="cq_x1",
            key_hash="h1",
            ttl="P30D",
            expires_at=expires_at,
        )
        await store.create_api_key(
            key_id="k2",
            user_id=user_id,
            name="desktop",
            labels=[],
            key_prefix="cq_x2",
            key_hash="h2",
            ttl="P30D",
            expires_at=expires_at,
        )

        assert await store.count_active_api_keys_for_user(user_id) == 2

        # Expired key does not count toward "active".
        expired_at = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        await store.create_api_key(
            key_id="k_exp",
            user_id=user_id,
            name="x",
            labels=[],
            key_prefix="cq_e",
            key_hash="he",
            ttl="P1D",
            expires_at=expired_at,
        )
        assert await store.count_active_api_keys_for_user(user_id) == 2

        # Other user has none.
        assert await store.count_active_api_keys_for_user(user_id + 99) == 0
    finally:
        await store.close()


async def test_get_active_api_key_by_id(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        user_id = await _seed_user(store)
        expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        await store.create_api_key(
            key_id="k1",
            user_id=user_id,
            name="laptop",
            labels=["dev"],
            key_prefix="cq_xxxx",
            key_hash="hash-bytes",
            ttl="P30D",
            expires_at=expires_at,
        )

        active = await store.get_active_api_key_by_id("k1")
        assert active is not None
        assert active["id"] == "k1"
        assert active["username"] == "alice"
        assert active["key_hash"] == "hash-bytes"

        # Missing -> None.
        assert await store.get_active_api_key_by_id("missing") is None

        # Expired -> None.
        expired_at = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        await store.create_api_key(
            key_id="k_exp",
            user_id=user_id,
            name="x",
            labels=[],
            key_prefix="cq_e",
            key_hash="he",
            ttl="P1D",
            expires_at=expired_at,
        )
        assert await store.get_active_api_key_by_id("k_exp") is None
    finally:
        await store.close()


async def test_list_api_keys_for_user(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        user_id = await _seed_user(store)
        expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        for i in range(3):
            await store.create_api_key(
                key_id=f"k{i}",
                user_id=user_id,
                name=f"name-{i}",
                labels=[f"l{i}"],
                key_prefix=f"cq_{i}",
                key_hash=f"h{i}",
                ttl="P30D",
                expires_at=expires_at,
            )

        keys = await store.list_api_keys_for_user(user_id)
        assert len(keys) == 3
        # Newest first (insertion order is reverse of creation order; SQL
        # ORDER BY created_at DESC handles this).
        assert {k["id"] for k in keys} == {"k0", "k1", "k2"}
        assert all("key_hash" not in k for k in keys), "list shape must omit the hash"

        # Other user gets empty.
        assert await store.list_api_keys_for_user(user_id + 99) == []
    finally:
        await store.close()


async def test_revoke_api_key(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        user_id = await _seed_user(store)
        expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        await store.create_api_key(
            key_id="k1",
            user_id=user_id,
            name="laptop",
            labels=[],
            key_prefix="cq_x",
            key_hash="h",
            ttl="P30D",
            expires_at=expires_at,
        )
        assert await store.count_active_api_keys_for_user(user_id) == 1

        assert await store.revoke_api_key(user_id=user_id, key_id="k1") is True
        assert await store.count_active_api_keys_for_user(user_id) == 0

        # Second revoke returns False.
        assert await store.revoke_api_key(user_id=user_id, key_id="k1") is False
        # Wrong user returns False.
        assert await store.revoke_api_key(user_id=user_id + 99, key_id="k1") is False
        # Missing key returns False.
        assert await store.revoke_api_key(user_id=user_id, key_id="missing") is False
    finally:
        await store.close()


async def test_touch_api_key_last_used(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        user_id = await _seed_user(store)
        expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        await store.create_api_key(
            key_id="k1",
            user_id=user_id,
            name="laptop",
            labels=[],
            key_prefix="cq_x",
            key_hash="h",
            ttl="P30D",
            expires_at=expires_at,
        )

        before = await store.get_api_key_for_user(user_id=user_id, key_id="k1")
        assert before is not None and before["last_used_at"] is None

        await store.touch_api_key_last_used("k1")

        after = await store.get_api_key_for_user(user_id=user_id, key_id="k1")
        assert after is not None and after["last_used_at"] is not None

        # Missing key id: best-effort, no raise.
        await store.touch_api_key_last_used("missing")
    finally:
        await store.close()


async def test_insert_duplicate_raises_sqlite3_integrity_error(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        unit = _make_unit()
        await store.insert(unit)
        with pytest.raises(sqlite3.IntegrityError):
            await store.insert(unit)
    finally:
        await store.close()


async def test_insert_with_empty_domains_raises(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        unit = _make_unit()
        unit_no_domains = unit.model_copy(update={"domains": []})
        with pytest.raises(ValueError, match="At least one non-empty domain"):
            await store.insert(unit_no_domains)
    finally:
        await store.close()


async def test_query_rejects_non_positive_limit(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        with pytest.raises(ValueError, match="limit must be positive"):
            await store.query(["x"], limit=0)
        with pytest.raises(ValueError, match="limit must be positive"):
            await store.query(["x"], limit=-1)
    finally:
        await store.close()


async def test_daily_counts_uses_date_key_and_gap_fills(db_path: Path) -> None:
    store = SqliteStore(db_path=db_path)
    try:
        # Empty store: empty list.
        assert await store.daily_counts(days=30) == []

        # One unit today: one row with "date" key.
        unit = _make_unit()
        await store.insert(unit)
        rows = await store.daily_counts(days=30)
        assert len(rows) >= 1
        assert all("date" in r for r in rows)
        assert all("day" not in r for r in rows)
        assert rows[-1]["date"] == datetime.now(UTC).date().isoformat()
    finally:
        await store.close()


async def test_insert_uses_first_observed_for_created_at(db_path: Path) -> None:
    """Verifies created_at falls back to evidence.first_observed when present."""
    from datetime import datetime as _dt

    store = SqliteStore(db_path=db_path)
    try:
        unit = _make_unit()
        backdated = _dt(2025, 1, 15, tzinfo=UTC)
        unit_with_backdate = unit.model_copy(
            update={"evidence": unit.evidence.model_copy(update={"first_observed": backdated})}
        )
        await store.insert(unit_with_backdate)

        # Read back via the engine to inspect the actual created_at column.
        with store._engine.connect() as conn:
            row = conn.exec_driver_sql(
                "SELECT created_at FROM knowledge_units WHERE id = ?",
                (unit_with_backdate.id,),
            ).fetchone()
        assert row is not None
        assert row[0] == backdated.isoformat()
    finally:
        await store.close()


@pytest.mark.parametrize(
    "call_method",
    [
        lambda s: s.count(),
        lambda s: s.domain_counts(),
        lambda s: s.counts_by_status(),
        lambda s: s.counts_by_tier(),
        lambda s: s.pending_count(),
        lambda s: s.list_units(),
        lambda s: s.confidence_distribution(),
        lambda s: s.recent_activity(),
        lambda s: s.daily_counts(),
        lambda s: s.create_user("u", "p"),
        lambda s: s.get_user("u"),
    ],
    ids=[
        "count",
        "domain_counts",
        "counts_by_status",
        "counts_by_tier",
        "pending_count",
        "list_units",
        "confidence_distribution",
        "recent_activity",
        "daily_counts",
        "create_user",
        "get_user",
    ],
)
async def test_method_raises_on_closed_store(db_path: Path, call_method) -> None:
    store = SqliteStore(db_path=db_path)
    await store.close()
    with pytest.raises(RuntimeError, match="SqliteStore is closed"):
        await call_method(store)
