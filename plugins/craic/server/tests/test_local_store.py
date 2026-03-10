import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from craic_mcp.knowledge_unit import (
    Context,
    Evidence,
    FlagReason,
    Insight,
    KnowledgeUnit,
    Tier,
    create_knowledge_unit,
)
from craic_mcp.local_store import LocalStore
from craic_mcp.scoring import apply_confirmation, apply_flag


def _make_insight(**overrides: Any) -> Insight:
    defaults = {
        "summary": "Use connection pooling",
        "detail": "Database connections are expensive to create.",
        "action": "Configure a connection pool with a max size of 10.",
    }
    return Insight(**{**defaults, **overrides})


def _make_unit(**overrides: Any) -> KnowledgeUnit:
    defaults = {
        "domain": ["databases", "performance"],
        "insight": _make_insight(),
    }
    return create_knowledge_unit(**{**defaults, **overrides})


def _inspect_domains(db_path: Path, unit_id: str) -> list[str]:
    """Read domain tags directly from SQLite for test assertions."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT domain FROM knowledge_unit_domains WHERE unit_id = ? ORDER BY domain",
            (unit_id,),
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def _inspect_tables(db_path: Path) -> list[str]:
    """List user tables in the SQLite database."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[LocalStore]:
    s = LocalStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


class TestAutoCreateSchema:
    def test_creates_database_file(self, tmp_path: Path):
        db_path = tmp_path / "subdir" / "nested" / "test.db"
        store = LocalStore(db_path=db_path)
        store.close()
        assert db_path.exists()

    def test_creates_knowledge_units_table(self, store: LocalStore):
        tables = _inspect_tables(store.db_path)
        assert "knowledge_units" in tables

    def test_creates_domains_table(self, store: LocalStore):
        tables = _inspect_tables(store.db_path)
        assert "knowledge_unit_domains" in tables

    def test_idempotent_schema_creation(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        store1 = LocalStore(db_path=db_path)
        store1.close()
        store2 = LocalStore(db_path=db_path)
        store2.close()


class TestContextManager:
    def test_usable_as_context_manager(self, tmp_path: Path):
        with LocalStore(db_path=tmp_path / "test.db") as store:
            unit = _make_unit()
            store.insert(unit)
            assert store.get(unit.id) == unit

    def test_close_is_idempotent(self, tmp_path: Path):
        store = LocalStore(db_path=tmp_path / "test.db")
        store.close()
        store.close()

    def test_operations_after_close_raise(self, tmp_path: Path):
        store = LocalStore(db_path=tmp_path / "test.db")
        store.close()
        with pytest.raises(RuntimeError, match="LocalStore is closed"):
            store.insert(_make_unit())
        with pytest.raises(RuntimeError, match="LocalStore is closed"):
            store.get("ku_any")
        with pytest.raises(RuntimeError, match="LocalStore is closed"):
            store.update(_make_unit())
        with pytest.raises(RuntimeError, match="LocalStore is closed"):
            store.query(["databases"])


class TestInsert:
    def test_insert_and_retrieve(self, store: LocalStore):
        unit = _make_unit()
        store.insert(unit)
        retrieved = store.get(unit.id)
        assert retrieved == unit

    def test_insert_duplicate_raises(self, store: LocalStore):
        unit = _make_unit()
        store.insert(unit)
        with pytest.raises(sqlite3.IntegrityError):
            store.insert(unit)

    def test_insert_stores_domain_tags(self, store: LocalStore):
        unit = _make_unit(domain=["api", "payments", "stripe"])
        store.insert(unit)
        domains = _inspect_domains(store.db_path, unit.id)
        assert domains == ["api", "payments", "stripe"]

    def test_insert_with_empty_domains_raises(self, store: LocalStore):
        unit = _make_unit(domain=["  ", ""])
        with pytest.raises(ValueError, match="At least one non-empty domain"):
            store.insert(unit)


class TestGet:
    def test_returns_none_for_missing_id(self, store: LocalStore):
        assert store.get("ku_nonexistent") is None

    def test_roundtrip_preserves_all_fields(self, store: LocalStore):
        unit = _make_unit(
            domain=["api"],
            context=Context(languages=["python"], frameworks=["django"], pattern="web-api"),
            tier=Tier.LOCAL,
            created_by="agent:test-machine",
        )
        store.insert(unit)
        retrieved = store.get(unit.id)
        assert retrieved is not None
        assert retrieved.domain == unit.domain
        assert retrieved.context == unit.context
        assert retrieved.tier == unit.tier
        assert retrieved.created_by == unit.created_by
        assert retrieved.evidence == unit.evidence
        assert retrieved.insight == unit.insight


class TestUpdate:
    def test_update_persists_changes(self, store: LocalStore):
        unit = _make_unit()
        store.insert(unit)

        confirmed = apply_confirmation(unit)
        store.update(confirmed)

        retrieved = store.get(unit.id)
        assert retrieved is not None
        assert retrieved.evidence.confirmations == 2
        assert retrieved.evidence.confidence == pytest.approx(0.6)

    def test_update_missing_unit_raises(self, store: LocalStore):
        unit = _make_unit()
        with pytest.raises(KeyError, match="Knowledge unit not found"):
            store.update(unit)

    def test_update_with_empty_domains_raises(self, store: LocalStore):
        unit = _make_unit(domain=["databases"])
        store.insert(unit)
        updated = unit.model_copy(update={"domain": ["  ", ""]})
        with pytest.raises(ValueError, match="At least one non-empty domain"):
            store.update(updated)

    def test_update_refreshes_domain_tags(self, store: LocalStore):
        unit = _make_unit(domain=["databases"])
        store.insert(unit)

        updated = unit.model_copy(update={"domain": ["databases", "caching"]})
        store.update(updated)

        retrieved = store.get(unit.id)
        assert retrieved is not None
        assert set(retrieved.domain) == {"databases", "caching"}

    def test_update_after_flag_reduces_confidence(self, store: LocalStore):
        unit = _make_unit()
        store.insert(unit)

        flagged = apply_flag(unit, FlagReason.STALE)
        store.update(flagged)

        retrieved = store.get(unit.id)
        assert retrieved is not None
        assert retrieved.evidence.confidence == pytest.approx(0.35)
        assert len(retrieved.flags) == 1


class TestQuery:
    def test_returns_units_with_matching_domain(self, store: LocalStore):
        unit = _make_unit(domain=["databases", "performance"])
        store.insert(unit)

        results = store.query(["databases"])
        assert len(results) == 1
        assert results[0].id == unit.id

    def test_returns_empty_for_no_match(self, store: LocalStore):
        unit = _make_unit(domain=["databases"])
        store.insert(unit)

        results = store.query(["networking"])
        assert results == []

    def test_returns_empty_for_empty_domains(self, store: LocalStore):
        unit = _make_unit(domain=["databases"])
        store.insert(unit)

        results = store.query([])
        assert results == []

    def test_rejects_non_positive_limit(self, store: LocalStore):
        with pytest.raises(ValueError, match="limit must be positive"):
            store.query(["databases"], limit=0)
        with pytest.raises(ValueError, match="limit must be positive"):
            store.query(["databases"], limit=-1)

    def test_ranks_by_domain_overlap(self, store: LocalStore):
        high_relevance = _make_unit(domain=["databases", "performance"])
        low_relevance = _make_unit(domain=["databases", "networking"])
        store.insert(high_relevance)
        store.insert(low_relevance)

        results = store.query(["databases", "performance"])
        assert len(results) == 2
        assert results[0].id == high_relevance.id

    def test_respects_limit(self, store: LocalStore):
        for _ in range(10):
            store.insert(_make_unit(domain=["databases"]))

        results = store.query(["databases"], limit=3)
        assert len(results) == 3

    def test_filters_by_language(self, store: LocalStore):
        python_unit = _make_unit(
            domain=["databases"],
            context=Context(languages=["python"]),
        )
        go_unit = _make_unit(
            domain=["databases"],
            context=Context(languages=["go"]),
        )
        store.insert(python_unit)
        store.insert(go_unit)

        results = store.query(["databases"], language="python")
        assert len(results) == 1
        assert results[0].id == python_unit.id

    def test_filters_by_framework(self, store: LocalStore):
        django_unit = _make_unit(
            domain=["web"],
            context=Context(frameworks=["django"]),
        )
        flask_unit = _make_unit(
            domain=["web"],
            context=Context(frameworks=["flask"]),
        )
        store.insert(django_unit)
        store.insert(flask_unit)

        results = store.query(["web"], framework="django")
        assert len(results) == 1
        assert results[0].id == django_unit.id

    def test_combined_language_and_framework_filter(self, store: LocalStore):
        match = _make_unit(
            domain=["web"],
            context=Context(languages=["python"], frameworks=["django"]),
        )
        partial = _make_unit(
            domain=["web"],
            context=Context(languages=["python"], frameworks=["flask"]),
        )
        store.insert(match)
        store.insert(partial)

        results = store.query(["web"], language="python", framework="django")
        assert len(results) == 1
        assert results[0].id == match.id

    def test_higher_confidence_ranks_higher(self, store: LocalStore):
        low_conf = _make_unit(domain=["databases"])
        high_conf = _make_unit(domain=["databases"])

        store.insert(low_conf)
        store.insert(high_conf)

        confirmed = apply_confirmation(high_conf)
        confirmed = apply_confirmation(confirmed)
        store.update(confirmed)

        results = store.query(["databases"])
        assert results[0].id == high_conf.id


class TestDomainNormalisation:
    def test_stores_domains_as_lowercase(self, store: LocalStore):
        unit = _make_unit(domain=["API", "Payments"])
        store.insert(unit)
        domains = _inspect_domains(store.db_path, unit.id)
        assert domains == ["api", "payments"]

    def test_strips_whitespace_from_domains(self, store: LocalStore):
        unit = _make_unit(domain=["  api  ", "payments "])
        store.insert(unit)
        domains = _inspect_domains(store.db_path, unit.id)
        assert domains == ["api", "payments"]

    def test_case_insensitive_query(self, store: LocalStore):
        unit = _make_unit(domain=["API", "Payments"])
        store.insert(unit)

        results = store.query(["api"])
        assert len(results) == 1
        assert results[0].id == unit.id

    def test_mixed_case_query_matches(self, store: LocalStore):
        unit = _make_unit(domain=["databases"])
        store.insert(unit)

        results = store.query(["Databases"])
        assert len(results) == 1
        assert results[0].id == unit.id

    def test_deduplicates_after_normalisation(self, store: LocalStore):
        unit = _make_unit(domain=["API", "api", "Api"])
        store.insert(unit)
        domains = _inspect_domains(store.db_path, unit.id)
        assert domains == ["api"]

    def test_filters_empty_and_whitespace_domains(self, store: LocalStore):
        unit = _make_unit(domain=["api", "  ", ""])
        store.insert(unit)
        domains = _inspect_domains(store.db_path, unit.id)
        assert domains == ["api"]

    def test_normalised_domains_persisted_in_blob(self, store: LocalStore):
        unit = _make_unit(domain=["API", "Payments"])
        store.insert(unit)
        retrieved = store.get(unit.id)
        assert retrieved is not None
        assert retrieved.domain == ["api", "payments"]

    def test_query_with_whitespace_only_domains_returns_empty(self, store: LocalStore):
        unit = _make_unit(domain=["databases"])
        store.insert(unit)
        results = store.query(["  ", ""])
        assert results == []


class TestEndToEnd:
    def test_insert_confirm_query_flag_lifecycle(self, store: LocalStore):
        unit = _make_unit(
            domain=["api", "payments"],
            context=Context(languages=["python"], frameworks=["fastapi"]),
        )
        store.insert(unit)

        results = store.query(["api", "payments"], language="python")
        assert len(results) == 1
        assert results[0].evidence.confidence == 0.5

        confirmed = apply_confirmation(results[0])
        store.update(confirmed)
        results = store.query(["api", "payments"])
        assert results[0].evidence.confidence == pytest.approx(0.6)
        assert results[0].evidence.confirmations == 2

        flagged = apply_flag(results[0], FlagReason.STALE)
        store.update(flagged)
        results = store.query(["api", "payments"])
        assert results[0].evidence.confidence == pytest.approx(0.45)
        assert len(results[0].flags) == 1

    def test_context_manager_lifecycle(self, tmp_path: Path):
        db_path = tmp_path / "lifecycle.db"
        unit = _make_unit(domain=["testing"])

        with LocalStore(db_path=db_path) as store:
            store.insert(unit)

        with LocalStore(db_path=db_path) as store:
            retrieved = store.get(unit.id)
            assert retrieved == unit


class TestStats:
    def test_empty_store_returns_zero_counts(self, store: LocalStore):
        result = store.stats()
        assert result.total_count == 0
        assert result.domain_counts == {}
        assert result.recent == []
        assert result.confidence_distribution == {
            "0.0-0.3": 0,
            "0.3-0.5": 0,
            "0.5-0.7": 0,
            "0.7-1.0": 0,
        }

    def test_total_count_matches_inserted_units(self, store: LocalStore):
        for _ in range(3):
            store.insert(_make_unit(domain=["api"]))
        result = store.stats()
        assert result.total_count == 3

    def test_domain_counts_across_multiple_units(self, store: LocalStore):
        store.insert(_make_unit(domain=["api", "payments"]))
        store.insert(_make_unit(domain=["api", "databases"]))
        store.insert(_make_unit(domain=["databases"]))
        result = store.stats()
        assert result.domain_counts == {"api": 2, "databases": 2, "payments": 1}

    def test_recent_ordered_by_last_confirmed_descending(self, store: LocalStore):
        now = datetime.now(UTC)
        old_unit = _make_unit(
            domain=["api"],
            context=Context(languages=["python"]),
        )
        old_unit = old_unit.model_copy(
            update={
                "evidence": Evidence(
                    first_observed=now - timedelta(days=10),
                    last_confirmed=now - timedelta(days=10),
                ),
            },
        )
        new_unit = _make_unit(
            domain=["api"],
            context=Context(languages=["go"]),
        )
        new_unit = new_unit.model_copy(
            update={
                "evidence": Evidence(
                    first_observed=now - timedelta(days=1),
                    last_confirmed=now - timedelta(days=1),
                ),
            },
        )
        store.insert(old_unit)
        store.insert(new_unit)

        result = store.stats()
        assert len(result.recent) == 2
        assert result.recent[0].id == new_unit.id
        assert result.recent[1].id == old_unit.id

    def test_recent_respects_limit(self, store: LocalStore):
        for _ in range(10):
            store.insert(_make_unit(domain=["api"]))
        result = store.stats(recent_limit=3)
        assert len(result.recent) == 3

    def test_confidence_distribution_buckets(self, store: LocalStore):
        # Default confidence is 0.5, which falls in "0.5-0.7".
        unit_mid = _make_unit(domain=["api"])
        store.insert(unit_mid)

        # Confirm twice to reach 0.7, which falls in "0.7-1.0".
        high_unit = _make_unit(domain=["api"])
        store.insert(high_unit)
        confirmed = apply_confirmation(high_unit)
        confirmed = apply_confirmation(confirmed)
        store.update(confirmed)

        # Flag twice to reach 0.2, which falls in "0.0-0.3".
        low_unit = _make_unit(domain=["api"])
        store.insert(low_unit)
        flagged = apply_flag(low_unit, FlagReason.STALE)
        flagged = apply_flag(flagged, FlagReason.STALE)
        store.update(flagged)

        # Flag once to reach 0.35, which falls in "0.3-0.5".
        mid_low_unit = _make_unit(domain=["api"])
        store.insert(mid_low_unit)
        flagged_once = apply_flag(mid_low_unit, FlagReason.STALE)
        store.update(flagged_once)

        result = store.stats()
        assert result.confidence_distribution == {
            "0.0-0.3": 1,
            "0.3-0.5": 1,
            "0.5-0.7": 1,
            "0.7-1.0": 1,
        }

    def test_stats_rejects_negative_recent_limit(self, store: LocalStore):
        with pytest.raises(ValueError, match="recent_limit must be non-negative"):
            store.stats(recent_limit=-1)

    def test_stats_allows_zero_recent_limit(self, store: LocalStore):
        store.insert(_make_unit(domain=["api"]))
        result = store.stats(recent_limit=0)
        assert result.total_count == 1
        assert result.recent == []

    def test_stats_raises_when_store_closed(self, tmp_path: Path):
        s = LocalStore(db_path=tmp_path / "test.db")
        s.close()
        with pytest.raises(RuntimeError, match="LocalStore is closed"):
            s.stats()
