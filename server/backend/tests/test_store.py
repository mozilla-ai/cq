"""Tests for the SQLite-backed remote knowledge store."""

import sqlite3
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from cq.models import (
    Context,
    FlagReason,
    Insight,
    KnowledgeUnit,
    Tier,
    create_knowledge_unit,
)

from cq_server.scoring import apply_confirmation, apply_flag
from cq_server.store import SqliteStore


def _make_insight(**overrides: Any) -> Insight:
    defaults = {
        "summary": "Use connection pooling",
        "detail": "Database connections are expensive to create.",
        "action": "Configure a connection pool with a max size of 10.",
    }
    return Insight(**{**defaults, **overrides})


def _make_unit(**overrides: Any) -> KnowledgeUnit:
    defaults = {
        "domains": ["databases", "performance"],
        "insight": _make_insight(),
    }
    return create_knowledge_unit(**{**defaults, **overrides})


@pytest_asyncio.fixture()
async def store(tmp_path: Path) -> AsyncIterator[SqliteStore]:
    s = SqliteStore(db_path=tmp_path / "test.db")
    try:
        yield s
    finally:
        await s.close()


async def _insert_and_approve(store: SqliteStore, **overrides: Any) -> KnowledgeUnit:
    """Insert a knowledge unit and approve it for query visibility."""
    unit = _make_unit(**overrides)
    await store.insert(unit)
    await store.set_review_status(unit.id, "approved", "test-reviewer")
    return unit


class TestInsertAndGet:
    async def test_insert_and_retrieve(self, store: SqliteStore) -> None:
        unit = _make_unit()
        await store.insert(unit)
        retrieved = await store.get_any(unit.id)
        assert retrieved == unit

    async def test_insert_duplicate_raises(self, store: SqliteStore) -> None:
        unit = _make_unit()
        await store.insert(unit)
        with pytest.raises(sqlite3.IntegrityError):
            await store.insert(unit)

    async def test_returns_none_for_missing_id(self, store: SqliteStore) -> None:
        assert await store.get("ku_nonexistent") is None

    async def test_insert_with_empty_domains_raises(self, store: SqliteStore) -> None:
        unit = _make_unit(domains=["  ", ""])
        with pytest.raises(ValueError, match="At least one non-empty domain"):
            await store.insert(unit)

    async def test_insert_persists_normalized_domains_in_blob(self, store: SqliteStore) -> None:
        # The JSON blob's domains must match the normalized rows in
        # knowledge_unit_domains; calculate_relevance reads unit.domains
        # from the blob and would mis-rank if the two diverge.
        unit = _make_unit(domains=["Databases", " Performance "])
        await store.insert(unit)
        retrieved = await store.get_any(unit.id)
        assert retrieved is not None
        assert retrieved.domains == ["databases", "performance"]


class TestUpdate:
    async def test_update_persists_changes(self, store: SqliteStore) -> None:
        unit = await _insert_and_approve(store)
        confirmed = apply_confirmation(unit)
        await store.update(confirmed)
        retrieved = await store.get(unit.id)
        assert retrieved is not None
        assert retrieved.evidence.confirmations == 2

    async def test_update_missing_unit_raises(self, store: SqliteStore) -> None:
        unit = _make_unit()
        with pytest.raises(KeyError, match="Knowledge unit not found"):
            await store.update(unit)

    async def test_update_with_empty_domains_raises(self, store: SqliteStore) -> None:
        unit = _make_unit(domains=["databases"])
        await store.insert(unit)
        updated = unit.model_copy(update={"domains": ["  "]})
        with pytest.raises(ValueError, match="At least one non-empty domain"):
            await store.update(updated)

    async def test_update_persists_normalized_domains_in_blob(self, store: SqliteStore) -> None:
        # As with insert: JSON blob's domains must match the normalized rows.
        unit = _make_unit(domains=["databases"])
        await store.insert(unit)
        updated = unit.model_copy(update={"domains": ["Databases", " Performance "]})
        await store.update(updated)
        retrieved = await store.get_any(unit.id)
        assert retrieved is not None
        assert retrieved.domains == ["databases", "performance"]


class TestQuery:
    async def test_returns_matching_units(self, store: SqliteStore) -> None:
        unit = await _insert_and_approve(store, domains=["databases"])
        results = await store.query(["databases"])
        assert len(results) == 1
        assert results[0].id == unit.id

    async def test_returns_empty_for_no_match(self, store: SqliteStore) -> None:
        await _insert_and_approve(store, domains=["databases"])
        assert await store.query(["networking"]) == []

    async def test_language_filter_boosts_matching_units(self, store: SqliteStore) -> None:
        py = await _insert_and_approve(
            store,
            domains=["web"],
            context=Context(languages=["python"]),
        )
        go = await _insert_and_approve(
            store,
            domains=["web"],
            context=Context(languages=["go"]),
        )
        results = await store.query(["web"], languages=["python"])
        assert len(results) == 2
        assert results[0].id == py.id
        assert results[1].id == go.id

    async def test_language_filter_includes_units_without_language(self, store: SqliteStore) -> None:
        """KUs with no language set should still appear when language filter is used."""
        no_lang = await _insert_and_approve(store, domains=["ci"])
        results = await store.query(["ci"], languages=["python"])
        assert len(results) == 1
        assert results[0].id == no_lang.id

    async def test_framework_filter_includes_units_without_framework(self, store: SqliteStore) -> None:
        """KUs with no framework set should still appear when framework filter is used."""
        no_fw = await _insert_and_approve(store, domains=["web"])
        results = await store.query(["web"], frameworks=["fastapi"])
        assert len(results) == 1
        assert results[0].id == no_fw.id

    async def test_language_filter_ranks_matching_higher(self, store: SqliteStore) -> None:
        """KUs with matching language should rank above those without."""
        no_lang = await _insert_and_approve(store, domains=["web"])
        with_lang = await _insert_and_approve(
            store,
            domains=["web"],
            context=Context(languages=["python"]),
        )
        results = await store.query(["web"], languages=["python"])
        assert len(results) == 2
        assert results[0].id == with_lang.id
        assert results[1].id == no_lang.id

    async def test_multiple_languages_boost_any_match(self, store: SqliteStore) -> None:
        """Querying with multiple languages boosts units matching any of them."""
        py = await _insert_and_approve(
            store,
            domains=["web"],
            context=Context(languages=["python"]),
        )
        go = await _insert_and_approve(
            store,
            domains=["web"],
            context=Context(languages=["go"]),
        )
        rust = await _insert_and_approve(
            store,
            domains=["web"],
            context=Context(languages=["rust"]),
        )
        results = await store.query(["web"], languages=["python", "go"])
        assert len(results) == 3
        # Both python and go units rank above rust (no match).
        matched_ids = {results[0].id, results[1].id}
        assert matched_ids == {py.id, go.id}
        assert results[2].id == rust.id

    async def test_multiple_frameworks_boost_any_match(self, store: SqliteStore) -> None:
        """Querying with multiple frameworks boosts units matching any of them."""
        fastapi = await _insert_and_approve(
            store,
            domains=["web"],
            context=Context(frameworks=["fastapi"]),
        )
        django = await _insert_and_approve(
            store,
            domains=["web"],
            context=Context(frameworks=["django"]),
        )
        flask = await _insert_and_approve(
            store,
            domains=["web"],
            context=Context(frameworks=["flask"]),
        )
        results = await store.query(["web"], frameworks=["fastapi", "django"])
        assert len(results) == 3
        matched_ids = {results[0].id, results[1].id}
        assert matched_ids == {fastapi.id, django.id}
        assert results[2].id == flask.id

    async def test_pattern_filter_boosts_matching_unit(self, store: SqliteStore) -> None:
        """KUs whose context.pattern matches the query pattern should rank above those that do not."""
        matching = await _insert_and_approve(
            store,
            domains=["api"],
            context=Context(pattern="api-client"),
        )
        plain = await _insert_and_approve(store, domains=["api"])
        results = await store.query(["api"], pattern="api-client")
        assert len(results) == 2
        assert results[0].id == matching.id
        assert results[1].id == plain.id

    async def test_rejects_non_positive_limit(self, store: SqliteStore) -> None:
        with pytest.raises(ValueError, match="limit must be positive"):
            await store.query(["databases"], limit=0)

    async def test_tie_break_orders_by_id_descending(self, store: SqliteStore) -> None:
        # Two units with identical context produce identical scores; the
        # tie-break must order by id descending (preserves the previous
        # RemoteStore semantics).
        a = await _insert_and_approve(store, domains=["databases"])
        b = await _insert_and_approve(store, domains=["databases"])
        results = await store.query(["databases"])
        assert {r.id for r in results} == {a.id, b.id}
        higher_id = max(a.id, b.id)
        assert results[0].id == higher_id


class TestStats:
    async def test_count_empty_store(self, store: SqliteStore) -> None:
        assert await store.count() == 0

    async def test_count_after_inserts(self, store: SqliteStore) -> None:
        await store.insert(_make_unit(domains=["a"]))
        await store.insert(_make_unit(domains=["b"]))
        assert await store.count() == 2

    async def test_domain_counts(self, store: SqliteStore) -> None:
        u1 = _make_unit(domains=["api", "payments"])
        u2 = _make_unit(domains=["api", "auth"])
        await store.insert(u1)
        await store.insert(u2)
        await store.set_review_status(u1.id, "approved", "tester")
        await store.set_review_status(u2.id, "approved", "tester")
        counts = await store.domain_counts()
        assert counts["api"] == 2
        assert counts["payments"] == 1
        assert counts["auth"] == 1


class TestTierColumn:
    async def test_tier_column_exists_after_migration(self, store: SqliteStore) -> None:
        """The tier column should exist on the knowledge_units table."""
        with store._engine.connect() as conn:
            cursor = conn.exec_driver_sql("PRAGMA table_info(knowledge_units)")
            columns = {row[1] for row in cursor.fetchall()}
        assert "tier" in columns

    async def test_tier_column_defaults_to_private_for_migration(self, store: SqliteStore) -> None:
        """Pre-existing rows without an explicit tier get 'private' from the column default."""
        with store._engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO knowledge_units (id, data, created_at) VALUES (?, ?, ?)",
                ("ku_00000000000000000000000000000001", "{}", "2026-01-01T00:00:00Z"),
            )
        with store._engine.connect() as conn:
            row = conn.exec_driver_sql(
                "SELECT tier FROM knowledge_units WHERE id = ?",
                ("ku_00000000000000000000000000000001",),
            ).fetchone()
        assert row[0] == "private"

    async def test_insert_populates_tier_from_unit(self, store: SqliteStore) -> None:
        """Insert should write the unit's tier value to the tier column."""
        unit = _make_unit(tier=Tier.PRIVATE)
        await store.insert(unit)
        with store._engine.connect() as conn:
            row = conn.exec_driver_sql("SELECT tier FROM knowledge_units WHERE id = ?", (unit.id,)).fetchone()
        assert row[0] == "private"

    async def test_update_syncs_tier_column(self, store: SqliteStore) -> None:
        """Update should keep the tier column in sync with the JSON blob."""
        unit = _make_unit(tier=Tier.PRIVATE)
        await store.insert(unit)
        updated = unit.model_copy(update={"tier": Tier.PUBLIC})
        await store.update(updated)
        with store._engine.connect() as conn:
            row = conn.exec_driver_sql("SELECT tier FROM knowledge_units WHERE id = ?", (unit.id,)).fetchone()
        assert row[0] == "public"

    async def test_counts_by_tier_empty(self, store: SqliteStore) -> None:
        """Empty store returns empty dict."""
        assert await store.counts_by_tier() == {}

    async def test_counts_by_tier_approved_only(self, store: SqliteStore) -> None:
        """Only approved units are counted."""
        u1 = _make_unit(domains=["a"], tier=Tier.PRIVATE)
        u2 = _make_unit(domains=["b"], tier=Tier.PRIVATE)
        u3 = _make_unit(domains=["c"], tier=Tier.PRIVATE)
        await store.insert(u1)
        await store.insert(u2)
        await store.insert(u3)
        await store.set_review_status(u1.id, "approved", "reviewer")
        await store.set_review_status(u2.id, "approved", "reviewer")
        counts = await store.counts_by_tier()
        assert counts == {"private": 2}

    async def test_counts_by_tier_groups_correctly(self, store: SqliteStore) -> None:
        """Counts are grouped by tier value."""
        u1 = _make_unit(domains=["a"], tier=Tier.PRIVATE)
        u2 = _make_unit(domains=["b"], tier=Tier.PUBLIC)
        await store.insert(u1)
        await store.insert(u2)
        await store.set_review_status(u1.id, "approved", "reviewer")
        await store.set_review_status(u2.id, "approved", "reviewer")
        counts = await store.counts_by_tier()
        assert counts == {"private": 1, "public": 1}


class TestReviewStatus:
    async def test_inserted_unit_has_pending_status(self, store: SqliteStore) -> None:
        unit = _make_unit()
        await store.insert(unit)
        status = await store.get_review_status(unit.id)
        assert status is not None
        assert status["status"] == "pending"
        assert status["reviewed_by"] is None
        assert status["reviewed_at"] is None


class TestStatusFiltering:
    async def test_query_excludes_pending_units(self, store: SqliteStore) -> None:
        unit = _make_unit(domains=["api"])
        await store.insert(unit)
        results = await store.query(["api"])
        assert len(results) == 0

    async def test_query_returns_approved_units(self, store: SqliteStore) -> None:
        unit = _make_unit(domains=["api"])
        await store.insert(unit)
        await store.set_review_status(unit.id, "approved", "reviewer")
        results = await store.query(["api"])
        assert len(results) == 1

    async def test_query_excludes_rejected_units(self, store: SqliteStore) -> None:
        unit = _make_unit(domains=["api"])
        await store.insert(unit)
        await store.set_review_status(unit.id, "rejected", "reviewer")
        results = await store.query(["api"])
        assert len(results) == 0

    async def test_get_only_returns_approved_for_agents(self, store: SqliteStore) -> None:
        unit = _make_unit()
        await store.insert(unit)
        assert await store.get(unit.id) is None

    async def test_get_returns_approved_unit(self, store: SqliteStore) -> None:
        unit = _make_unit()
        await store.insert(unit)
        await store.set_review_status(unit.id, "approved", "reviewer")
        assert await store.get(unit.id) is not None


class TestReviewQueue:
    async def test_pending_queue_returns_pending_units(self, store: SqliteStore) -> None:
        u1 = _make_unit(domains=["api"])
        u2 = _make_unit(domains=["db"])
        await store.insert(u1)
        await store.insert(u2)
        queue = await store.pending_queue(limit=20, offset=0)
        assert len(queue) == 2

    async def test_pending_queue_excludes_reviewed(self, store: SqliteStore) -> None:
        unit = _make_unit(domains=["api"])
        await store.insert(unit)
        await store.set_review_status(unit.id, "approved", "reviewer")
        queue = await store.pending_queue(limit=20, offset=0)
        assert len(queue) == 0

    async def test_pending_count(self, store: SqliteStore) -> None:
        u1 = _make_unit(domains=["a"])
        u2 = _make_unit(domains=["b"])
        await store.insert(u1)
        await store.insert(u2)
        await store.set_review_status(u1.id, "approved", "reviewer")
        assert await store.pending_count() == 1

    async def test_counts_by_status(self, store: SqliteStore) -> None:
        u1 = _make_unit(domains=["a"])
        u2 = _make_unit(domains=["b"])
        u3 = _make_unit(domains=["c"])
        await store.insert(u1)
        await store.insert(u2)
        await store.insert(u3)
        await store.set_review_status(u1.id, "approved", "reviewer")
        await store.set_review_status(u2.id, "rejected", "reviewer")
        counts = await store.counts_by_status()
        assert counts["approved"] == 1
        assert counts["rejected"] == 1
        assert counts["pending"] == 1

    async def test_daily_counts(self, store: SqliteStore) -> None:
        await store.insert(_make_unit(domains=["a"]))
        await store.insert(_make_unit(domains=["b"]))
        counts = await store.daily_counts(days=30)
        assert len(counts) >= 1
        total = sum(row["proposed"] for row in counts)
        assert total == 2

    async def test_daily_counts_gap_fills_to_today(self, store: SqliteStore) -> None:
        """daily_counts should return contiguous dates from the earliest entry to today."""
        three_days_ago = datetime.now(UTC) - timedelta(days=3)
        unit = _make_unit(domains=["a"])
        unit.evidence.first_observed = three_days_ago
        unit.evidence.last_confirmed = three_days_ago
        await store.insert(unit)

        counts = await store.daily_counts(days=30)

        dates = [row["date"] for row in counts]
        today_str = datetime.now(UTC).strftime("%Y-%m-%d")
        three_days_ago_str = three_days_ago.strftime("%Y-%m-%d")

        # Should include every date from the earliest entry through today.
        assert dates[0] == three_days_ago_str
        assert dates[-1] == today_str
        assert len(dates) == 4  # 3 days ago, 2 days ago, yesterday, today

        # Only the first date has a proposal; rest should be zero.
        assert counts[0]["proposed"] == 1
        for row in counts[1:]:
            assert row["proposed"] == 0

    async def test_daily_counts_includes_approved(self, store: SqliteStore) -> None:
        """daily_counts should include approved counts grouped by reviewed_at date."""
        three_days_ago = datetime.now(UTC) - timedelta(days=3)
        one_day_ago = datetime.now(UTC) - timedelta(days=1)

        u1 = _make_unit(domains=["a"])
        u1.evidence.first_observed = three_days_ago
        u1.evidence.last_confirmed = three_days_ago
        await store.insert(u1)

        u2 = _make_unit(domains=["b"])
        u2.evidence.first_observed = three_days_ago
        u2.evidence.last_confirmed = three_days_ago
        await store.insert(u2)

        await store.set_review_status(u1.id, "approved", "reviewer")
        # Backdate reviewed_at to 1 day ago.
        with store._engine.begin() as conn:
            conn.exec_driver_sql(
                "UPDATE knowledge_units SET reviewed_at = ? WHERE id = ?",
                (one_day_ago.isoformat(), u1.id),
            )

        counts = await store.daily_counts(days=30)
        by_date = {row["date"]: row for row in counts}

        three_days_ago_str = three_days_ago.strftime("%Y-%m-%d")
        one_day_ago_str = one_day_ago.strftime("%Y-%m-%d")

        # Both units were proposed 3 days ago.
        assert by_date[three_days_ago_str]["proposed"] == 2
        # One was approved 1 day ago.
        assert by_date[one_day_ago_str]["approved"] == 1
        # No approvals on the proposal date.
        assert by_date[three_days_ago_str]["approved"] == 0

    async def test_daily_counts_includes_rejected(self, store: SqliteStore) -> None:
        """daily_counts should include rejected counts grouped by reviewed_at date."""
        two_days_ago = datetime.now(UTC) - timedelta(days=2)

        unit = _make_unit(domains=["a"])
        unit.evidence.first_observed = two_days_ago
        unit.evidence.last_confirmed = two_days_ago
        await store.insert(unit)

        await store.set_review_status(unit.id, "rejected", "reviewer")
        # Backdate reviewed_at to today.
        today = datetime.now(UTC)
        with store._engine.begin() as conn:
            conn.exec_driver_sql(
                "UPDATE knowledge_units SET reviewed_at = ? WHERE id = ?",
                (today.isoformat(), unit.id),
            )

        counts = await store.daily_counts(days=30)
        by_date = {row["date"]: row for row in counts}

        today_str = today.strftime("%Y-%m-%d")
        two_days_ago_str = two_days_ago.strftime("%Y-%m-%d")

        assert by_date[two_days_ago_str]["proposed"] == 1
        assert by_date[two_days_ago_str]["rejected"] == 0
        assert by_date[today_str]["rejected"] == 1
        assert by_date[today_str]["proposed"] == 0

    async def test_daily_counts_rejects_non_positive_days(self, store: SqliteStore) -> None:
        with pytest.raises(ValueError, match="days must be positive"):
            await store.daily_counts(days=0)

    async def test_pending_queue_pagination(self, store: SqliteStore) -> None:
        for _ in range(3):
            await store.insert(_make_unit(domains=["a"]))
        page1 = await store.pending_queue(limit=2, offset=0)
        page2 = await store.pending_queue(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 1
        ids = {r["knowledge_unit"].id for r in page1} | {r["knowledge_unit"].id for r in page2}
        assert len(ids) == 3

    async def test_counts_by_status_empty(self, store: SqliteStore) -> None:
        counts = await store.counts_by_status()
        assert counts == {}


class TestApiKeys:
    @staticmethod
    async def _seed_user(store: SqliteStore, username: str = "alice") -> int:
        await store.create_user(username, "hash-unused")
        user = await store.get_user(username)
        assert user is not None
        return int(user["id"])

    @staticmethod
    def _future(days: int = 30) -> str:
        return (datetime.now(UTC) + timedelta(days=days)).isoformat()

    @staticmethod
    def _past(days: int = 1) -> str:
        return (datetime.now(UTC) - timedelta(days=days)).isoformat()

    async def test_create_and_fetch_active_by_id(self, store: SqliteStore) -> None:
        user_id = await self._seed_user(store)
        row = await store.create_api_key(
            key_id="k1",
            user_id=user_id,
            name="laptop",
            labels=[],
            key_prefix="abcdefgh",
            key_hash="hash-1",
            ttl="30d",
            expires_at=self._future(),
        )
        assert row["id"] == "k1"
        assert row["revoked_at"] is None

        fetched = await store.get_active_api_key_by_id("k1")
        assert fetched is not None
        assert fetched["id"] == "k1"
        assert fetched["username"] == "alice"
        assert fetched["user_id"] == user_id
        assert fetched["name"] == "laptop"
        assert fetched["key_hash"] == "hash-1"

    async def test_get_active_by_id_missing(self, store: SqliteStore) -> None:
        assert await store.get_active_api_key_by_id("nope") is None

    async def test_get_active_by_id_excludes_revoked(self, store: SqliteStore) -> None:
        user_id = await self._seed_user(store)
        await store.create_api_key(
            key_id="k1",
            user_id=user_id,
            name="laptop",
            labels=[],
            key_prefix="abcdefgh",
            key_hash="hash-1",
            ttl="30d",
            expires_at=self._future(),
        )
        assert await store.revoke_api_key(user_id=user_id, key_id="k1") is True
        assert await store.get_active_api_key_by_id("k1") is None

    async def test_create_rejects_duplicate_hash(self, store: SqliteStore) -> None:
        user_id = await self._seed_user(store)
        await store.create_api_key(
            key_id="k1",
            user_id=user_id,
            name="a",
            labels=[],
            key_prefix="cqa_1",
            key_hash="dup",
            ttl="30d",
            expires_at=self._future(),
        )
        with pytest.raises(sqlite3.IntegrityError):
            await store.create_api_key(
                key_id="k2",
                user_id=user_id,
                name="b",
                labels=[],
                key_prefix="cqa_2",
                key_hash="dup",
                ttl="30d",
                expires_at=self._future(),
            )

    async def test_list_for_user_orders_newest_first(self, store: SqliteStore) -> None:
        user_id = await self._seed_user(store)
        await store.create_api_key(
            key_id="k1",
            user_id=user_id,
            name="first",
            labels=[],
            key_prefix="cqa_1",
            key_hash="h1",
            ttl="30d",
            expires_at=self._future(),
        )
        await store.create_api_key(
            key_id="k2",
            user_id=user_id,
            name="second",
            labels=[],
            key_prefix="cqa_2",
            key_hash="h2",
            ttl="30d",
            expires_at=self._future(),
        )
        rows = await store.list_api_keys_for_user(user_id)
        assert [r["id"] for r in rows] == ["k2", "k1"]
        assert all("key_hash" not in r for r in rows)

    async def test_list_scoped_by_user(self, store: SqliteStore) -> None:
        alice_id = await self._seed_user(store, "alice")
        bob_id = await self._seed_user(store, "bob")
        await store.create_api_key(
            key_id="k-alice",
            user_id=alice_id,
            name="a",
            labels=[],
            key_prefix="cqa_a",
            key_hash="ha",
            ttl="30d",
            expires_at=self._future(),
        )
        await store.create_api_key(
            key_id="k-bob",
            user_id=bob_id,
            name="b",
            labels=[],
            key_prefix="cqa_b",
            key_hash="hb",
            ttl="30d",
            expires_at=self._future(),
        )
        assert [r["id"] for r in await store.list_api_keys_for_user(alice_id)] == ["k-alice"]
        assert [r["id"] for r in await store.list_api_keys_for_user(bob_id)] == ["k-bob"]

    async def test_count_active_excludes_revoked_and_expired(self, store: SqliteStore) -> None:
        user_id = await self._seed_user(store)
        await store.create_api_key(
            key_id="active",
            user_id=user_id,
            name="a",
            labels=[],
            key_prefix="cqa_a",
            key_hash="h-a",
            ttl="30d",
            expires_at=self._future(),
        )
        await store.create_api_key(
            key_id="expired",
            user_id=user_id,
            name="e",
            labels=[],
            key_prefix="cqa_e",
            key_hash="h-e",
            ttl="30d",
            expires_at=self._past(),
        )
        await store.create_api_key(
            key_id="revoked",
            user_id=user_id,
            name="r",
            labels=[],
            key_prefix="cqa_r",
            key_hash="h-r",
            ttl="30d",
            expires_at=self._future(),
        )
        assert await store.revoke_api_key(user_id=user_id, key_id="revoked") is True

        assert await store.count_active_api_keys_for_user(user_id) == 1

    async def test_revoke_scoped_to_owner(self, store: SqliteStore) -> None:
        alice_id = await self._seed_user(store, "alice")
        bob_id = await self._seed_user(store, "bob")
        await store.create_api_key(
            key_id="k",
            user_id=alice_id,
            name="a",
            labels=[],
            key_prefix="cqa_",
            key_hash="h",
            ttl="30d",
            expires_at=self._future(),
        )
        assert await store.revoke_api_key(user_id=bob_id, key_id="k") is False
        assert await store.revoke_api_key(user_id=alice_id, key_id="k") is True
        assert await store.revoke_api_key(user_id=alice_id, key_id="k") is False

    async def test_revoke_missing_key(self, store: SqliteStore) -> None:
        user_id = await self._seed_user(store)
        assert await store.revoke_api_key(user_id=user_id, key_id="nope") is False

    async def test_touch_last_used_updates_timestamp(self, store: SqliteStore) -> None:
        user_id = await self._seed_user(store)
        await store.create_api_key(
            key_id="k",
            user_id=user_id,
            name="a",
            labels=[],
            key_prefix="cqa_",
            key_hash="h",
            ttl="30d",
            expires_at=self._future(),
        )
        assert (await store.get_active_api_key_by_id("k"))["last_used_at"] is None
        await store.touch_api_key_last_used("k")
        assert (await store.get_active_api_key_by_id("k"))["last_used_at"] is not None

    async def test_touch_last_used_missing_key_swallowed(self, store: SqliteStore) -> None:
        await store.touch_api_key_last_used("nonexistent")  # No raise.

    async def test_get_user_includes_id(self, store: SqliteStore) -> None:
        await store.create_user("alice", "hash")
        user = await store.get_user("alice")
        assert user is not None
        assert isinstance(user["id"], int)


class TestEndToEnd:
    async def test_propose_confirm_flag_lifecycle(self, store: SqliteStore) -> None:
        await _insert_and_approve(
            store,
            domains=["api", "payments"],
            context=Context(languages=["python"], frameworks=["fastapi"]),
            tier=Tier.PRIVATE,
        )

        results = await store.query(["api", "payments"], languages=["python"])
        assert len(results) == 1
        assert results[0].evidence.confidence == 0.5

        confirmed = apply_confirmation(results[0])
        await store.update(confirmed)
        results = await store.query(["api", "payments"])
        assert results[0].evidence.confidence == pytest.approx(0.6)

        flagged = apply_flag(results[0], FlagReason.STALE)
        await store.update(flagged)
        results = await store.query(["api", "payments"])
        assert results[0].evidence.confidence == pytest.approx(0.45)
        assert len(results[0].flags) == 1
