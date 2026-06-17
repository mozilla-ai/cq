"""Backend-agnostic conformance suite for the Store SPI.

Any Store implementation (the default SqliteStore, a first-party adapter,
or a bring-your-own store) must exhibit identical observable behavior.
``run_store_conformance`` exercises the eight SPI methods against a fresh
store and asserts that behavior, so an implementer reuses it as their
acceptance test. ``conformance_store_factories`` lists the in-tree stores;
``tests/test_store_conformance.py`` parametrizes the suite over them.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cq.models import Context, Evidence, Insight, KnowledgeUnit, create_knowledge_unit
from cq.scoring import apply_confirmation
from cq.store import (
    _MAX_QUERY_FRAMEWORKS,
    _MAX_QUERY_LANGUAGES,
    _MAX_QUERY_LIMIT,
    DuplicateUnitError,
    QueryParams,
    SqliteStore,
    Store,
)
from cq.stores import InMemoryStore

StoreFactory = Callable[[], Store]


def _make_unit(**overrides: object) -> KnowledgeUnit:
    """Build a knowledge unit with sensible conformance defaults."""
    defaults: dict[str, object] = {
        "domains": ["databases", "performance"],
        "insight": Insight(
            summary="Use connection pooling",
            detail="Database connections are expensive to create.",
            action="Configure a connection pool with a max size of 10.",
        ),
    }
    return create_knowledge_unit(**{**defaults, **overrides})  # type: ignore[arg-type]


def run_store_conformance(make_store: StoreFactory) -> None:
    """Assert that ``make_store`` yields a Store with the required behavior.

    Args:
        make_store: A callable returning a fresh, empty Store on each call.
            Each scenario builds its own store so the suite never depends
            on cross-scenario state.
    """
    _assert_is_store(make_store)
    _assert_insert_get_roundtrip(make_store)
    _assert_get_missing_returns_none(make_store)
    _assert_duplicate_insert_raises(make_store)
    _assert_empty_domains_raises(make_store)
    _assert_update_existing(make_store)
    _assert_update_missing_raises(make_store)
    _assert_delete_existing(make_store)
    _assert_delete_missing_raises(make_store)
    _assert_all_returns_every_unit(make_store)
    _assert_query_ranks_by_relevance_and_confidence(make_store)
    _assert_query_respects_limit(make_store)
    _assert_query_returns_domain_matches(make_store)
    _assert_query_limit_zero_defaults_negative_raises(make_store)
    _assert_query_bounds_reject_excess(make_store)
    _assert_stats_aggregates(make_store)
    _assert_close_is_idempotent_and_blocks_ops(make_store)


def _assert_is_store(make_store: StoreFactory) -> None:
    store = make_store()
    try:
        assert isinstance(store, Store)
    finally:
        store.close()


def _assert_insert_get_roundtrip(make_store: StoreFactory) -> None:
    store = make_store()
    try:
        unit = _make_unit()
        store.insert(unit)
        assert store.get(unit.id) == unit
    finally:
        store.close()


def _assert_get_missing_returns_none(make_store: StoreFactory) -> None:
    store = make_store()
    try:
        assert store.get("ku_ffffffffffffffffffffffffffffffff") is None
    finally:
        store.close()


def _assert_duplicate_insert_raises(make_store: StoreFactory) -> None:
    store = make_store()
    try:
        unit = _make_unit()
        store.insert(unit)
        with pytest.raises(DuplicateUnitError):
            store.insert(unit)
    finally:
        store.close()


def _assert_empty_domains_raises(make_store: StoreFactory) -> None:
    store = make_store()
    try:
        unit = _make_unit(domains=["  ", ""])
        with pytest.raises(ValueError, match="At least one non-empty domain"):
            store.insert(unit)
    finally:
        store.close()


def _assert_update_existing(make_store: StoreFactory) -> None:
    store = make_store()
    try:
        unit = _make_unit()
        store.insert(unit)
        confirmed = apply_confirmation(unit)
        store.update(confirmed)
        retrieved = store.get(unit.id)
        assert retrieved is not None
        assert retrieved.evidence.confirmations == 2
    finally:
        store.close()


def _assert_update_missing_raises(make_store: StoreFactory) -> None:
    store = make_store()
    try:
        with pytest.raises(KeyError, match="Knowledge unit not found"):
            store.update(_make_unit())
    finally:
        store.close()


def _assert_delete_existing(make_store: StoreFactory) -> None:
    store = make_store()
    try:
        unit = _make_unit(domains=["api"])
        store.insert(unit)
        store.delete(unit.id)
        assert store.get(unit.id) is None
    finally:
        store.close()


def _assert_delete_missing_raises(make_store: StoreFactory) -> None:
    store = make_store()
    try:
        with pytest.raises(KeyError, match="Knowledge unit not found"):
            store.delete("ku_ffffffffffffffffffffffffffffffff")
    finally:
        store.close()


def _assert_all_returns_every_unit(make_store: StoreFactory) -> None:
    store = make_store()
    try:
        assert store.all() == []
        u1 = _make_unit(domains=["api"])
        u2 = _make_unit(domains=["databases"])
        store.insert(u1)
        store.insert(u2)
        assert {u.id for u in store.all()} == {u1.id, u2.id}
    finally:
        store.close()


def _assert_query_ranks_by_relevance_and_confidence(make_store: StoreFactory) -> None:
    store = make_store()
    try:
        high_relevance = _make_unit(domains=["databases", "performance"])
        low_relevance = _make_unit(domains=["databases", "networking"])
        store.insert(high_relevance)
        store.insert(low_relevance)
        result = store.query(QueryParams(domains=["databases", "performance"]))
        assert len(result.units) == 2
        assert result.units[0].id == high_relevance.id

        # Confidence breaks the tie when relevance is equal.
        low_conf = _make_unit(domains=["caching"])
        high_conf = _make_unit(domains=["caching"])
        store.insert(low_conf)
        store.insert(apply_confirmation(apply_confirmation(high_conf)))
        ranked = store.query(QueryParams(domains=["caching"]))
        assert ranked.units[0].id == high_conf.id
    finally:
        store.close()


def _assert_query_respects_limit(make_store: StoreFactory) -> None:
    store = make_store()
    try:
        for _ in range(10):
            store.insert(_make_unit(domains=["databases"]))
        result = store.query(QueryParams(domains=["databases"], limit=3))
        assert len(result.units) == 3
    finally:
        store.close()


def _assert_query_returns_domain_matches(make_store: StoreFactory) -> None:
    store = make_store()
    try:
        unit = _make_unit(domains=["databases", "performance"])
        store.insert(unit)
        match = store.query(QueryParams(domains=["databases"]))
        assert [u.id for u in match.units] == [unit.id]
        miss = store.query(QueryParams(domains=["networking"]))
        assert miss.units == []
        empty = store.query(QueryParams(domains=[]))
        assert empty.units == []
    finally:
        store.close()


def _assert_query_limit_zero_defaults_negative_raises(make_store: StoreFactory) -> None:
    store = make_store()
    try:
        for _ in range(7):
            store.insert(_make_unit(domains=["databases"]))
        # Zero limit means "unset": the store falls back to its default (5).
        result = store.query(QueryParams(domains=["databases"], limit=0))
        assert len(result.units) == 5
        with pytest.raises(ValueError, match="limit must be positive"):
            store.query(QueryParams(domains=["databases"], limit=-1))
    finally:
        store.close()


def _assert_query_bounds_reject_excess(make_store: StoreFactory) -> None:
    store = make_store()
    try:
        store.insert(_make_unit(domains=["databases"]))
        with pytest.raises(ValueError, match="limit must be at most"):
            store.query(QueryParams(domains=["databases"], limit=_MAX_QUERY_LIMIT + 1))
        with pytest.raises(ValueError, match="languages"):
            store.query(
                QueryParams(domains=["databases"], languages=[f"l{i}" for i in range(_MAX_QUERY_LANGUAGES + 1)])
            )
        with pytest.raises(ValueError, match="frameworks"):
            store.query(
                QueryParams(domains=["databases"], frameworks=[f"f{i}" for i in range(_MAX_QUERY_FRAMEWORKS + 1)])
            )
    finally:
        store.close()


def _assert_stats_aggregates(make_store: StoreFactory) -> None:
    store = make_store()
    try:
        empty = store.stats()
        assert empty.total_count == 0
        assert empty.confidence_distribution == {
            "0.0-0.3": 0,
            "0.3-0.5": 0,
            "0.5-0.7": 0,
            "0.7-1.0": 0,
        }

        now = datetime.now(UTC)
        old_when = now - timedelta(days=10)
        new_when = now - timedelta(days=1)
        older = _make_unit(domains=["api", "payments"]).model_copy(
            update={"evidence": Evidence(first_observed=old_when, last_confirmed=old_when)}
        )
        newer = _make_unit(domains=["api", "databases"], context=Context(languages=["go"])).model_copy(
            update={"evidence": Evidence(first_observed=new_when, last_confirmed=new_when)}
        )
        store.insert(older)
        store.insert(newer)

        stats = store.stats()
        assert stats.total_count == 2
        assert stats.domain_counts == {"api": 2, "databases": 1, "payments": 1}
        assert [u.id for u in stats.recent] == [newer.id, older.id]
        assert stats.confidence_distribution["0.5-0.7"] == 2

        with pytest.raises(ValueError, match="recent_limit must be non-negative"):
            store.stats(recent_limit=-1)
    finally:
        store.close()


def _assert_close_is_idempotent_and_blocks_ops(make_store: StoreFactory) -> None:
    store = make_store()
    store.close()
    store.close()
    with pytest.raises(RuntimeError):
        store.insert(_make_unit())
    with pytest.raises(RuntimeError):
        store.update(_make_unit())
    with pytest.raises(RuntimeError):
        store.delete("ku_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee")
    with pytest.raises(RuntimeError):
        store.get("ku_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee")
    with pytest.raises(RuntimeError):
        store.all()
    with pytest.raises(RuntimeError):
        store.query(QueryParams(domains=["databases"]))
    with pytest.raises(RuntimeError):
        store.stats()


def conformance_store_factories(tmp_path: Path) -> dict[str, StoreFactory]:
    """Return the in-tree Store factories keyed by a parametrization id.

    Each factory yields a fresh store; the SQLite factory uses a unique
    file under ``tmp_path`` per call so scenarios never share state.
    """
    counter = {"n": 0}

    def make_sqlite() -> Store:
        counter["n"] += 1
        return SqliteStore(db_path=tmp_path / f"conformance_{counter['n']}.db")

    return {
        "sqlite": make_sqlite,
        "memory": InMemoryStore,
    }
