"""Tests for the SQLite-backed remote knowledge store."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cq.models import (
    Context,
    FlagReason,
    Insight,
    KnowledgeUnit,
    Tier,
    create_knowledge_unit,
)

from cq_server.scoring import apply_confirmation, apply_flag
from cq_server.store import RemoteStore


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


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[RemoteStore]:
    s = RemoteStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


def _insert_and_approve(store: RemoteStore, **overrides: Any) -> KnowledgeUnit:
    """Insert a knowledge unit and approve it for query visibility."""
    unit = _make_unit(**overrides)
    store.insert(unit)
    store.set_review_status(unit.id, "approved", "test-reviewer")
    return unit


class TestInsertAndGet:
    def test_insert_and_retrieve(self, store: RemoteStore) -> None:
        unit = _make_unit()
        store.insert(unit)
        retrieved = store.get_any(unit.id)
        assert retrieved == unit

    def test_insert_duplicate_raises(self, store: RemoteStore) -> None:
        unit = _make_unit()
        store.insert(unit)
        with pytest.raises(sqlite3.IntegrityError):
            store.insert(unit)

    def test_returns_none_for_missing_id(self, store: RemoteStore) -> None:
        assert store.get("ku_nonexistent") is None

    def test_insert_with_empty_domains_raises(self, store: RemoteStore) -> None:
        unit = _make_unit(domains=["  ", ""])
        with pytest.raises(ValueError, match="At least one non-empty domain"):
            store.insert(unit)


class TestUpdate:
    def test_update_persists_changes(self, store: RemoteStore) -> None:
        unit = _insert_and_approve(store)
        confirmed = apply_confirmation(unit)
        store.update(confirmed)
        retrieved = store.get(unit.id)
        assert retrieved is not None
        assert retrieved.evidence.confirmations == 2

    def test_update_missing_unit_raises(self, store: RemoteStore) -> None:
        unit = _make_unit()
        with pytest.raises(KeyError, match="Knowledge unit not found"):
            store.update(unit)

    def test_update_with_empty_domains_raises(self, store: RemoteStore) -> None:
        unit = _make_unit(domains=["databases"])
        store.insert(unit)
        updated = unit.model_copy(update={"domains": ["  "]})
        with pytest.raises(ValueError, match="At least one non-empty domain"):
            store.update(updated)


class TestQuery:
    def test_returns_matching_units(self, store: RemoteStore) -> None:
        unit = _insert_and_approve(store, domains=["databases"])
        results = store.query(["databases"])
        assert len(results) == 1
        assert results[0].id == unit.id

    def test_returns_empty_for_no_match(self, store: RemoteStore) -> None:
        _insert_and_approve(store, domains=["databases"])
        assert store.query(["networking"]) == []

    def test_language_filter_boosts_matching_units(self, store: RemoteStore) -> None:
        py = _insert_and_approve(
            store,
            domains=["web"],
            context=Context(languages=["python"]),
        )
        go = _insert_and_approve(
            store,
            domains=["web"],
            context=Context(languages=["go"]),
        )
        results = store.query(["web"], languages=["python"])
        assert len(results) == 2
        assert results[0].id == py.id
        assert results[1].id == go.id

    def test_language_filter_includes_units_without_language(self, store: RemoteStore) -> None:
        """KUs with no language set should still appear when language filter is used."""
        no_lang = _insert_and_approve(store, domains=["ci"])
        results = store.query(["ci"], languages=["python"])
        assert len(results) == 1
        assert results[0].id == no_lang.id

    def test_framework_filter_includes_units_without_framework(self, store: RemoteStore) -> None:
        """KUs with no framework set should still appear when framework filter is used."""
        no_fw = _insert_and_approve(store, domains=["web"])
        results = store.query(["web"], frameworks=["fastapi"])
        assert len(results) == 1
        assert results[0].id == no_fw.id

    def test_language_filter_ranks_matching_higher(self, store: RemoteStore) -> None:
        """KUs with matching language should rank above those without."""
        no_lang = _insert_and_approve(store, domains=["web"])
        with_lang = _insert_and_approve(
            store,
            domains=["web"],
            context=Context(languages=["python"]),
        )
        results = store.query(["web"], languages=["python"])
        assert len(results) == 2
        assert results[0].id == with_lang.id
        assert results[1].id == no_lang.id

    def test_multiple_languages_boost_any_match(self, store: RemoteStore) -> None:
        """Querying with multiple languages boosts units matching any of them."""
        py = _insert_and_approve(
            store,
            domains=["web"],
            context=Context(languages=["python"]),
        )
        go = _insert_and_approve(
            store,
            domains=["web"],
            context=Context(languages=["go"]),
        )
        rust = _insert_and_approve(
            store,
            domains=["web"],
            context=Context(languages=["rust"]),
        )
        results = store.query(["web"], languages=["python", "go"])
        assert len(results) == 3
        # Both python and go units rank above rust (no match).
        matched_ids = {results[0].id, results[1].id}
        assert matched_ids == {py.id, go.id}
        assert results[2].id == rust.id

    def test_multiple_frameworks_boost_any_match(self, store: RemoteStore) -> None:
        """Querying with multiple frameworks boosts units matching any of them."""
        fastapi = _insert_and_approve(
            store,
            domains=["web"],
            context=Context(frameworks=["fastapi"]),
        )
        django = _insert_and_approve(
            store,
            domains=["web"],
            context=Context(frameworks=["django"]),
        )
        flask = _insert_and_approve(
            store,
            domains=["web"],
            context=Context(frameworks=["flask"]),
        )
        results = store.query(["web"], frameworks=["fastapi", "django"])
        assert len(results) == 3
        matched_ids = {results[0].id, results[1].id}
        assert matched_ids == {fastapi.id, django.id}
        assert results[2].id == flask.id

    def test_rejects_non_positive_limit(self, store: RemoteStore) -> None:
        with pytest.raises(ValueError, match="limit must be positive"):
            store.query(["databases"], limit=0)


class TestStats:
    def test_count_empty_store(self, store: RemoteStore) -> None:
        assert store.count() == 0

    def test_count_after_inserts(self, store: RemoteStore) -> None:
        store.insert(_make_unit(domains=["a"]))
        store.insert(_make_unit(domains=["b"]))
        assert store.count() == 2

    def test_domain_counts(self, store: RemoteStore) -> None:
        u1 = _make_unit(domains=["api", "payments"])
        u2 = _make_unit(domains=["api", "auth"])
        store.insert(u1)
        store.insert(u2)
        store.set_review_status(u1.id, "approved", "tester")
        store.set_review_status(u2.id, "approved", "tester")
        counts = store.domain_counts()
        assert counts["api"] == 2
        assert counts["payments"] == 1
        assert counts["auth"] == 1


class TestTierColumn:
    def test_tier_column_exists_after_migration(self, store: RemoteStore) -> None:
        """The tier column should exist on the knowledge_units table."""
        cursor = store._conn.execute("PRAGMA table_info(knowledge_units)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "tier" in columns

    def test_tier_column_defaults_to_private_for_migration(self, store: RemoteStore) -> None:
        """Pre-existing rows without an explicit tier get 'private' from the column default."""
        store._conn.execute(
            "INSERT INTO knowledge_units (id, data, created_at) VALUES (?, ?, ?)",
            ("ku_00000000000000000000000000000001", "{}", "2026-01-01T00:00:00Z"),
        )
        store._conn.commit()
        row = store._conn.execute(
            "SELECT tier FROM knowledge_units WHERE id = ?",
            ("ku_00000000000000000000000000000001",),
        ).fetchone()
        assert row[0] == "private"

    def test_insert_populates_tier_from_unit(self, store: RemoteStore) -> None:
        """Insert should write the unit's tier value to the tier column."""
        unit = _make_unit(tier=Tier.PRIVATE)
        store.insert(unit)
        row = store._conn.execute("SELECT tier FROM knowledge_units WHERE id = ?", (unit.id,)).fetchone()
        assert row[0] == "private"

    def test_update_syncs_tier_column(self, store: RemoteStore) -> None:
        """Update should keep the tier column in sync with the JSON blob."""
        unit = _make_unit(tier=Tier.PRIVATE)
        store.insert(unit)
        updated = unit.model_copy(update={"tier": Tier.PUBLIC})
        store.update(updated)
        row = store._conn.execute("SELECT tier FROM knowledge_units WHERE id = ?", (unit.id,)).fetchone()
        assert row[0] == "public"

    def test_counts_by_tier_empty(self, store: RemoteStore) -> None:
        """Empty store returns empty dict."""
        assert store.counts_by_tier() == {}

    def test_counts_by_tier_approved_only(self, store: RemoteStore) -> None:
        """Only approved units are counted."""
        u1 = _make_unit(domains=["a"], tier=Tier.PRIVATE)
        u2 = _make_unit(domains=["b"], tier=Tier.PRIVATE)
        u3 = _make_unit(domains=["c"], tier=Tier.PRIVATE)
        store.insert(u1)
        store.insert(u2)
        store.insert(u3)
        store.set_review_status(u1.id, "approved", "reviewer")
        store.set_review_status(u2.id, "approved", "reviewer")
        counts = store.counts_by_tier()
        assert counts == {"private": 2}

    def test_counts_by_tier_groups_correctly(self, store: RemoteStore) -> None:
        """Counts are grouped by tier value."""
        u1 = _make_unit(domains=["a"], tier=Tier.PRIVATE)
        u2 = _make_unit(domains=["b"], tier=Tier.PUBLIC)
        store.insert(u1)
        store.insert(u2)
        store.set_review_status(u1.id, "approved", "reviewer")
        store.set_review_status(u2.id, "approved", "reviewer")
        counts = store.counts_by_tier()
        assert counts == {"private": 1, "public": 1}


class TestReviewStatus:
    def test_inserted_unit_has_pending_status(self, store: RemoteStore) -> None:
        unit = _make_unit()
        store.insert(unit)
        status = store.get_review_status(unit.id)
        assert status is not None
        assert status["status"] == "pending"
        assert status["reviewed_by"] is None
        assert status["reviewed_at"] is None


class TestStatusFiltering:
    def test_query_excludes_pending_units(self, store: RemoteStore) -> None:
        unit = _make_unit(domains=["api"])
        store.insert(unit)
        results = store.query(["api"])
        assert len(results) == 0

    def test_query_returns_approved_units(self, store: RemoteStore) -> None:
        unit = _make_unit(domains=["api"])
        store.insert(unit)
        store.set_review_status(unit.id, "approved", "reviewer")
        results = store.query(["api"])
        assert len(results) == 1

    def test_query_excludes_rejected_units(self, store: RemoteStore) -> None:
        unit = _make_unit(domains=["api"])
        store.insert(unit)
        store.set_review_status(unit.id, "rejected", "reviewer")
        results = store.query(["api"])
        assert len(results) == 0

    def test_get_only_returns_approved_for_agents(self, store: RemoteStore) -> None:
        unit = _make_unit()
        store.insert(unit)
        assert store.get(unit.id) is None

    def test_get_returns_approved_unit(self, store: RemoteStore) -> None:
        unit = _make_unit()
        store.insert(unit)
        store.set_review_status(unit.id, "approved", "reviewer")
        assert store.get(unit.id) is not None


class TestReviewQueue:
    def test_pending_queue_returns_pending_units(self, store: RemoteStore) -> None:
        u1 = _make_unit(domains=["api"])
        u2 = _make_unit(domains=["db"])
        store.insert(u1)
        store.insert(u2)
        queue = store.pending_queue(limit=20, offset=0)
        assert len(queue) == 2

    def test_pending_queue_excludes_reviewed(self, store: RemoteStore) -> None:
        unit = _make_unit(domains=["api"])
        store.insert(unit)
        store.set_review_status(unit.id, "approved", "reviewer")
        queue = store.pending_queue(limit=20, offset=0)
        assert len(queue) == 0

    def test_pending_count(self, store: RemoteStore) -> None:
        u1 = _make_unit(domains=["a"])
        u2 = _make_unit(domains=["b"])
        store.insert(u1)
        store.insert(u2)
        store.set_review_status(u1.id, "approved", "reviewer")
        assert store.pending_count() == 1

    def test_counts_by_status(self, store: RemoteStore) -> None:
        u1 = _make_unit(domains=["a"])
        u2 = _make_unit(domains=["b"])
        u3 = _make_unit(domains=["c"])
        store.insert(u1)
        store.insert(u2)
        store.insert(u3)
        store.set_review_status(u1.id, "approved", "reviewer")
        store.set_review_status(u2.id, "rejected", "reviewer")
        counts = store.counts_by_status()
        assert counts["approved"] == 1
        assert counts["rejected"] == 1
        assert counts["pending"] == 1

    def test_daily_counts(self, store: RemoteStore) -> None:
        store.insert(_make_unit(domains=["a"]))
        store.insert(_make_unit(domains=["b"]))
        counts = store.daily_counts(days=30)
        assert len(counts) >= 1
        total = sum(row["proposed"] for row in counts)
        assert total == 2

    def test_daily_counts_gap_fills_to_today(self, store: RemoteStore) -> None:
        """daily_counts should return contiguous dates from the earliest entry to today."""
        three_days_ago = datetime.now(UTC) - timedelta(days=3)
        unit = _make_unit(domains=["a"])
        unit.evidence.first_observed = three_days_ago
        unit.evidence.last_confirmed = three_days_ago
        store.insert(unit)

        counts = store.daily_counts(days=30)

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

    def test_daily_counts_includes_approved(self, store: RemoteStore) -> None:
        """daily_counts should include approved counts grouped by reviewed_at date."""
        three_days_ago = datetime.now(UTC) - timedelta(days=3)
        one_day_ago = datetime.now(UTC) - timedelta(days=1)

        u1 = _make_unit(domains=["a"])
        u1.evidence.first_observed = three_days_ago
        u1.evidence.last_confirmed = three_days_ago
        store.insert(u1)

        u2 = _make_unit(domains=["b"])
        u2.evidence.first_observed = three_days_ago
        u2.evidence.last_confirmed = three_days_ago
        store.insert(u2)

        store.set_review_status(u1.id, "approved", "reviewer")
        # Backdate reviewed_at to 1 day ago.
        with store._lock, store._conn:
            store._conn.execute(
                "UPDATE knowledge_units SET reviewed_at = ? WHERE id = ?",
                (one_day_ago.isoformat(), u1.id),
            )

        counts = store.daily_counts(days=30)
        by_date = {row["date"]: row for row in counts}

        three_days_ago_str = three_days_ago.strftime("%Y-%m-%d")
        one_day_ago_str = one_day_ago.strftime("%Y-%m-%d")

        # Both units were proposed 3 days ago.
        assert by_date[three_days_ago_str]["proposed"] == 2
        # One was approved 1 day ago.
        assert by_date[one_day_ago_str]["approved"] == 1
        # No approvals on the proposal date.
        assert by_date[three_days_ago_str]["approved"] == 0

    def test_daily_counts_includes_rejected(self, store: RemoteStore) -> None:
        """daily_counts should include rejected counts grouped by reviewed_at date."""
        two_days_ago = datetime.now(UTC) - timedelta(days=2)

        unit = _make_unit(domains=["a"])
        unit.evidence.first_observed = two_days_ago
        unit.evidence.last_confirmed = two_days_ago
        store.insert(unit)

        store.set_review_status(unit.id, "rejected", "reviewer")
        # Backdate reviewed_at to today.
        today = datetime.now(UTC)
        with store._lock, store._conn:
            store._conn.execute(
                "UPDATE knowledge_units SET reviewed_at = ? WHERE id = ?",
                (today.isoformat(), unit.id),
            )

        counts = store.daily_counts(days=30)
        by_date = {row["date"]: row for row in counts}

        today_str = today.strftime("%Y-%m-%d")
        two_days_ago_str = two_days_ago.strftime("%Y-%m-%d")

        assert by_date[two_days_ago_str]["proposed"] == 1
        assert by_date[two_days_ago_str]["rejected"] == 0
        assert by_date[today_str]["rejected"] == 1
        assert by_date[today_str]["proposed"] == 0

    def test_daily_counts_rejects_non_positive_days(self, store: RemoteStore) -> None:
        with pytest.raises(ValueError, match="days must be positive"):
            store.daily_counts(days=0)

    def test_pending_queue_pagination(self, store: RemoteStore) -> None:
        for _ in range(3):
            store.insert(_make_unit(domains=["a"]))
        page1 = store.pending_queue(limit=2, offset=0)
        page2 = store.pending_queue(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 1
        ids = {r["knowledge_unit"].id for r in page1} | {r["knowledge_unit"].id for r in page2}
        assert len(ids) == 3

    def test_counts_by_status_empty(self, store: RemoteStore) -> None:
        counts = store.counts_by_status()
        assert counts == {}


class TestEndToEnd:
    def test_propose_confirm_flag_lifecycle(self, store: RemoteStore) -> None:
        _insert_and_approve(
            store,
            domains=["api", "payments"],
            context=Context(languages=["python"], frameworks=["fastapi"]),
            tier=Tier.PRIVATE,
        )

        results = store.query(["api", "payments"], languages=["python"])
        assert len(results) == 1
        assert results[0].evidence.confidence == 0.5

        confirmed = apply_confirmation(results[0])
        store.update(confirmed)
        results = store.query(["api", "payments"])
        assert results[0].evidence.confidence == pytest.approx(0.6)

        flagged = apply_flag(results[0], FlagReason.STALE)
        store.update(flagged)
        results = store.query(["api", "payments"])
        assert results[0].evidence.confidence == pytest.approx(0.45)
        assert len(results[0].flags) == 1
