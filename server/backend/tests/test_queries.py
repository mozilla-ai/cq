"""Tests for the shared SQLAlchemy Core query helpers in ``store._queries``.

Each test binds the helper to an on-disk SQLite database that is also
managed by the existing ``SqliteStore``. ``SqliteStore`` sets up the
schema via its ``_ensure_schema()`` path and is used as the parity oracle:
results from the helpers must match whatever ``SqliteStore`` produces for
the same fixture data.

This avoids redeclaring the schema in test code and lets the issue land
without a dependency on the baseline Alembic migration (#305).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from cq.models import Insight, KnowledgeUnit, Tier, create_knowledge_unit
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError

from cq_server.store import SqliteStore
from cq_server.store import _queries as q


@pytest_asyncio.fixture()
async def db(tmp_path: Path) -> AsyncIterator[tuple[SqliteStore, Engine]]:
    """Shared on-disk SQLite database with both a SqliteStore and an SA engine."""
    db_path = tmp_path / "test.db"
    store = SqliteStore(db_path=db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        yield store, engine
    finally:
        engine.dispose()
        await store.close()


def _make_unit(**overrides: Any) -> KnowledgeUnit:
    defaults: dict[str, Any] = {
        "domains": ["databases", "performance"],
        "insight": Insight(
            summary="Use connection pooling",
            detail="Database connections are expensive to create.",
            action="Configure a connection pool with a max size of 10.",
        ),
    }
    return create_knowledge_unit(**{**defaults, **overrides})


async def _seed_user(store: SqliteStore, username: str = "alice") -> int:
    """Create a user and return its integer id."""
    await store.create_user(username, "hashed-pw")
    user = await store.get_user(username)
    assert user is not None
    return int(user["id"])


# --- knowledge_units: read helpers -----------------------------------------


class TestSelectByIdHelpers:
    async def test_select_approved_by_id(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        unit = _make_unit()
        await store.insert(unit)
        await store.set_review_status(unit.id, "approved", "reviewer")
        with engine.connect() as conn:
            row = conn.execute(q.SELECT_APPROVED_BY_ID, {"id": unit.id}).fetchone()
        assert row is not None
        assert KnowledgeUnit.model_validate_json(row[0]) == await store.get(unit.id)

    async def test_select_approved_by_id_skips_pending(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        unit = _make_unit()
        await store.insert(unit)
        with engine.connect() as conn:
            row = conn.execute(q.SELECT_APPROVED_BY_ID, {"id": unit.id}).fetchone()
        assert row is None

    async def test_select_by_id_returns_regardless_of_status(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        unit = _make_unit()
        await store.insert(unit)
        with engine.connect() as conn:
            row = conn.execute(q.SELECT_BY_ID, {"id": unit.id}).fetchone()
        assert row is not None
        assert KnowledgeUnit.model_validate_json(row[0]) == await store.get_any(unit.id)

    async def test_select_by_id_missing(self, db: tuple[SqliteStore, Engine]) -> None:
        _, engine = db
        with engine.connect() as conn:
            row = conn.execute(q.SELECT_BY_ID, {"id": "ku_missing"}).fetchone()
        assert row is None

    async def test_select_review_status_by_id(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        unit = _make_unit()
        await store.insert(unit)
        await store.set_review_status(unit.id, "approved", "reviewer")
        with engine.connect() as conn:
            row = conn.execute(q.SELECT_REVIEW_STATUS_BY_ID, {"id": unit.id}).fetchone()
        assert row is not None
        expected = await store.get_review_status(unit.id)
        assert {"status": row[0], "reviewed_by": row[1], "reviewed_at": row[2]} == expected


class TestAggregates:
    async def test_select_total_count(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        for _ in range(3):
            await store.insert(_make_unit())
        with engine.connect() as conn:
            row = conn.execute(q.SELECT_TOTAL_COUNT).fetchone()
        assert row is not None
        assert row[0] == await store.count() == 3

    async def test_select_pending_count(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        units = [_make_unit() for _ in range(3)]
        for u in units:
            await store.insert(u)
        await store.set_review_status(units[0].id, "approved", "rev")
        with engine.connect() as conn:
            row = conn.execute(q.SELECT_PENDING_COUNT).fetchone()
        assert row is not None
        assert row[0] == await store.pending_count() == 2

    async def test_select_counts_by_status(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        units = [_make_unit() for _ in range(3)]
        for u in units:
            await store.insert(u)
        await store.set_review_status(units[0].id, "approved", "rev")
        await store.set_review_status(units[1].id, "rejected", "rev")
        with engine.connect() as conn:
            rows = conn.execute(q.SELECT_COUNTS_BY_STATUS).fetchall()
        assert {row[0]: row[1] for row in rows} == await store.counts_by_status()

    async def test_select_counts_by_tier(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        u_local = _make_unit(tier=Tier.LOCAL)
        u_public = _make_unit(tier=Tier.PUBLIC)
        await store.insert(u_local)
        await store.insert(u_public)
        await store.set_review_status(u_local.id, "approved", "rev")
        await store.set_review_status(u_public.id, "approved", "rev")
        with engine.connect() as conn:
            rows = conn.execute(q.SELECT_COUNTS_BY_TIER).fetchall()
        assert {row[0]: row[1] for row in rows} == await store.counts_by_tier()

    async def test_select_domain_counts(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        unit_a = _make_unit(domains=["databases", "performance"])
        unit_b = _make_unit(domains=["databases"])
        await store.insert(unit_a)
        await store.insert(unit_b)
        await store.set_review_status(unit_a.id, "approved", "rev")
        await store.set_review_status(unit_b.id, "approved", "rev")
        with engine.connect() as conn:
            rows = conn.execute(q.SELECT_DOMAIN_COUNTS).fetchall()
        assert {row[0]: row[1] for row in rows} == await store.domain_counts()


class TestPendingQueue:
    async def test_select_pending_queue(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        units = [_make_unit() for _ in range(3)]
        for u in units:
            await store.insert(u)
        await store.set_review_status(units[0].id, "approved", "rev")
        with engine.connect() as conn:
            rows = conn.execute(q.SELECT_PENDING_QUEUE, {"limit": 10, "offset": 0}).fetchall()
        helper = [
            {
                "knowledge_unit": KnowledgeUnit.model_validate_json(row[0]),
                "status": row[1],
                "reviewed_by": row[2],
                "reviewed_at": row[3],
            }
            for row in rows
        ]
        assert helper == await store.pending_queue(limit=10, offset=0)

    async def test_select_pending_queue_offset(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        for _ in range(3):
            await store.insert(_make_unit())
        with engine.connect() as conn:
            rows = conn.execute(q.SELECT_PENDING_QUEUE, {"limit": 1, "offset": 1}).fetchall()
        assert len(rows) == 1


class TestApprovedDataAndActivity:
    async def test_select_approved_data(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        u_a = _make_unit()
        u_b = _make_unit()
        await store.insert(u_a)
        await store.insert(u_b)
        await store.set_review_status(u_a.id, "approved", "rev")
        with engine.connect() as conn:
            rows = conn.execute(q.SELECT_APPROVED_DATA).fetchall()
        ids = {KnowledgeUnit.model_validate_json(row[0]).id for row in rows}
        assert ids == {u_a.id}

    async def test_select_recent_activity(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        units = [_make_unit() for _ in range(3)]
        for u in units:
            await store.insert(u)
        await store.set_review_status(units[0].id, "approved", "rev")
        with engine.connect() as conn:
            rows = conn.execute(q.SELECT_RECENT_ACTIVITY, {"limit": 10}).fetchall()
        # Just assert shape and ordering hint: reviewed row appears once and
        # ordering matches SqliteStore's ORDER BY COALESCE(reviewed_at, created_at) DESC.
        assert len(rows) == 3
        ids = [row[0] for row in rows]
        assert units[0].id == ids[0]

    async def test_recent_activity_parity_with_store(self, db: tuple[SqliteStore, Engine]) -> None:
        """Helper feeds SqliteStore.recent_activity's exact pipeline (over-fetch + Python sort)."""
        store, engine = db
        units = [_make_unit() for _ in range(3)]
        for u in units:
            await store.insert(u)
        await store.set_review_status(units[0].id, "approved", "rev")
        await store.set_review_status(units[1].id, "rejected", "rev")
        limit = 5
        with engine.connect() as conn:
            rows = conn.execute(q.SELECT_RECENT_ACTIVITY, {"limit": limit * 2}).fetchall()
        # Mirror SqliteStore.recent_activity decoration verbatim.
        decorated: list[dict[str, Any]] = []
        for row in rows:
            unit = KnowledgeUnit.model_validate_json(row[1])
            proposed_ts = unit.evidence.first_observed.isoformat() if unit.evidence.first_observed else ""
            if row[2] in ("approved", "rejected"):
                decorated.append(
                    {
                        "type": row[2],
                        "unit_id": row[0],
                        "summary": unit.insight.summary,
                        "reviewed_by": row[3],
                        "timestamp": row[4] or proposed_ts,
                    }
                )
            else:
                decorated.append(
                    {
                        "type": "proposed",
                        "unit_id": row[0],
                        "summary": unit.insight.summary,
                        "timestamp": proposed_ts,
                    }
                )
        decorated.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        assert decorated[:limit] == await store.recent_activity(limit=limit)


class TestSelectQueryUnits:
    async def test_returns_approved_units_matching_any_domain(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        match = _make_unit(domains=["databases"])
        other = _make_unit(domains=["frontend"])
        pending = _make_unit(domains=["databases"])  # not approved -> excluded
        await store.insert(match)
        await store.insert(other)
        await store.insert(pending)
        await store.set_review_status(match.id, "approved", "rev")
        await store.set_review_status(other.id, "approved", "rev")
        with engine.connect() as conn:
            rows = conn.execute(q.SELECT_QUERY_UNITS, {"domains": ["databases"]}).fetchall()
        ids = {KnowledgeUnit.model_validate_json(row[0]).id for row in rows}
        assert ids == {match.id}

    async def test_empty_domains_list_returns_zero_rows(self, db: tuple[SqliteStore, Engine]) -> None:
        """Pin SQLAlchemy's empty-expanding-bind contract.

        SQLAlchemy 2.0 rewrites ``IN ()`` to a no-rows subquery so an empty
        ``:domains`` list yields zero rows rather than raising. This test
        fires if a future SQLAlchemy version reverts to raising or changes
        the rewrite — at which point the comment on ``SELECT_QUERY_UNITS``
        and any caller-side short-circuits need revisiting.
        """
        store, engine = db
        approved = _make_unit(domains=["databases"])
        await store.insert(approved)
        await store.set_review_status(approved.id, "approved", "rev")
        with engine.connect() as conn:
            rows = conn.execute(q.SELECT_QUERY_UNITS, {"domains": []}).fetchall()
        assert rows == []


class TestSelectListUnitsBuilder:
    async def test_no_filters_no_limit(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        for _ in range(3):
            await store.insert(_make_unit())
        stmt = q.select_list_units(domain=None, status=None, apply_limit=False)
        with engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        assert len(rows) == 3

    async def test_filter_by_status(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        u_a = _make_unit()
        u_b = _make_unit()
        await store.insert(u_a)
        await store.insert(u_b)
        await store.set_review_status(u_a.id, "approved", "rev")
        stmt = q.select_list_units(domain=None, status="approved", apply_limit=True)
        with engine.connect() as conn:
            rows = conn.execute(stmt, {"status": "approved", "limit": 10}).fetchall()
        ids = {KnowledgeUnit.model_validate_json(row[0]).id for row in rows}
        assert ids == {u_a.id}

    async def test_filter_by_domain(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        match = _make_unit(domains=["databases"])
        other = _make_unit(domains=["frontend"])
        await store.insert(match)
        await store.insert(other)
        stmt = q.select_list_units(domain="databases", status=None, apply_limit=True)
        with engine.connect() as conn:
            rows = conn.execute(stmt, {"domain": "databases", "limit": 10}).fetchall()
        ids = {KnowledgeUnit.model_validate_json(row[0]).id for row in rows}
        assert ids == {match.id}

    async def test_filter_by_domain_and_status(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        match = _make_unit(domains=["databases"])
        unapproved = _make_unit(domains=["databases"])
        wrong_domain = _make_unit(domains=["frontend"])
        for u in (match, unapproved, wrong_domain):
            await store.insert(u)
        await store.set_review_status(match.id, "approved", "rev")
        await store.set_review_status(wrong_domain.id, "approved", "rev")
        stmt = q.select_list_units(domain="databases", status="approved", apply_limit=True)
        with engine.connect() as conn:
            rows = conn.execute(stmt, {"domain": "databases", "status": "approved", "limit": 10}).fetchall()
        ids = {KnowledgeUnit.model_validate_json(row[0]).id for row in rows}
        assert ids == {match.id}

    async def test_parity_with_store_list_units(self, db: tuple[SqliteStore, Engine]) -> None:
        """Helper output, after SqliteStore-style decoration, matches store.list_units()."""
        store, engine = db
        u_pending = _make_unit(domains=["databases"])
        u_approved = _make_unit(domains=["databases"])
        u_rejected = _make_unit(domains=["frontend"])
        for u in (u_pending, u_approved, u_rejected):
            await store.insert(u)
        await store.set_review_status(u_approved.id, "approved", "rev")
        await store.set_review_status(u_rejected.id, "rejected", "rev")
        stmt = q.select_list_units(domain=None, status=None, apply_limit=True)
        with engine.connect() as conn:
            rows = conn.execute(stmt, {"limit": 100}).fetchall()
        decorated = [
            {
                "knowledge_unit": KnowledgeUnit.model_validate_json(row[0]),
                "status": row[1] or "pending",
                "reviewed_by": row[2],
                "reviewed_at": row[3],
            }
            for row in rows
        ]
        assert decorated == await store.list_units(limit=100)


def _backdate(engine: Engine, *, column: str, unit_id: str, when: datetime) -> None:
    """Backdate a timestamp column directly via the engine.

    Avoids reaching into ``SqliteStore`` internals so these tests survive
    the SQLAlchemy-backed ``SqliteStore`` rewrite in #308.
    """
    stmt = text(f"UPDATE knowledge_units SET {column} = :when WHERE id = :id")  # noqa: S608  (column whitelisted)
    with engine.begin() as conn:
        conn.execute(stmt, {"when": when.isoformat(), "id": unit_id})


class TestDailyCounts:
    """Cutoff is computed in Python per RFC #275."""

    async def test_proposed_daily(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        now = datetime.now(UTC)
        u_recent = _make_unit()
        u_old = _make_unit()
        await store.insert(u_recent)
        await store.insert(u_old)
        _backdate(engine, column="created_at", unit_id=u_old.id, when=now - timedelta(days=60))
        cutoff = (now - timedelta(days=30)).date().isoformat()
        with engine.connect() as conn:
            rows = conn.execute(q.SELECT_PROPOSED_DAILY, {"cutoff": cutoff}).fetchall()
        # u_old is older than the cutoff and excluded.
        assert sum(row[1] for row in rows) == 1

    async def test_approved_daily(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        now = datetime.now(UTC)
        u = _make_unit()
        await store.insert(u)
        await store.set_review_status(u.id, "approved", "rev")
        cutoff = (now - timedelta(days=30)).date().isoformat()
        with engine.connect() as conn:
            rows = conn.execute(q.SELECT_APPROVED_DAILY, {"cutoff": cutoff}).fetchall()
        assert sum(row[1] for row in rows) == 1

    async def test_rejected_daily_excludes_old(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        now = datetime.now(UTC)
        u = _make_unit()
        await store.insert(u)
        await store.set_review_status(u.id, "rejected", "rev")
        _backdate(engine, column="reviewed_at", unit_id=u.id, when=now - timedelta(days=60))
        cutoff = (now - timedelta(days=30)).date().isoformat()
        with engine.connect() as conn:
            rows = conn.execute(q.SELECT_REJECTED_DAILY, {"cutoff": cutoff}).fetchall()
        assert rows == []

    async def test_daily_helpers_match_store(self, db: tuple[SqliteStore, Engine]) -> None:
        """Assembled helper output matches ``SqliteStore.daily_counts()``.

        Builds the same merged/zero-filled shape ``daily_counts`` returns
        (one entry per day from the earliest activity through today), so a
        future change to a helper's column order, ``GROUP BY``, or filter
        will diverge here.
        """
        store, engine = db
        now = datetime.now(UTC)
        # Mix of recent + older activity across all three statuses, plus an
        # entry well outside the 30-day window to confirm the cutoff bites.
        u_pending = _make_unit()
        u_approved_recent = _make_unit()
        u_approved_old = _make_unit()
        u_rejected = _make_unit()
        u_outside = _make_unit()
        for u in (u_pending, u_approved_recent, u_approved_old, u_rejected, u_outside):
            await store.insert(u)
        await store.set_review_status(u_approved_recent.id, "approved", "rev")
        await store.set_review_status(u_approved_old.id, "approved", "rev")
        await store.set_review_status(u_rejected.id, "rejected", "rev")
        _backdate(engine, column="reviewed_at", unit_id=u_approved_old.id, when=now - timedelta(days=10))
        _backdate(engine, column="created_at", unit_id=u_approved_old.id, when=now - timedelta(days=10))
        _backdate(engine, column="created_at", unit_id=u_outside.id, when=now - timedelta(days=60))

        days = 30
        cutoff = (now - timedelta(days=days)).date().isoformat()
        with engine.connect() as conn:
            proposed_rows = conn.execute(q.SELECT_PROPOSED_DAILY, {"cutoff": cutoff}).fetchall()
            approved_rows = conn.execute(q.SELECT_APPROVED_DAILY, {"cutoff": cutoff}).fetchall()
            rejected_rows = conn.execute(q.SELECT_REJECTED_DAILY, {"cutoff": cutoff}).fetchall()
        proposed = {row[0]: row[1] for row in proposed_rows}
        approved = {row[0]: row[1] for row in approved_rows}
        rejected = {row[0]: row[1] for row in rejected_rows}
        all_dates = set(proposed) | set(approved) | set(rejected)
        assembled: list[dict[str, Any]] = []
        if all_dates:
            start = min(datetime.strptime(d, "%Y-%m-%d").date() for d in all_dates)
            end = datetime.now(UTC).date()
            current = start
            while current <= end:
                key = current.isoformat()
                assembled.append(
                    {
                        "date": key,
                        "proposed": proposed.get(key, 0),
                        "approved": approved.get(key, 0),
                        "rejected": rejected.get(key, 0),
                    }
                )
                current += timedelta(days=1)

        assert assembled == await store.daily_counts(days=days)


# --- knowledge_units: write helpers ----------------------------------------


class TestWriteHelpers:
    async def test_insert_unit_then_unit_domain(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        unit = _make_unit(domains=["databases", "performance"])
        created_at = datetime.now(UTC).isoformat()
        with engine.begin() as conn:
            conn.execute(
                q.INSERT_UNIT,
                {
                    "id": unit.id,
                    "data": unit.model_dump_json(),
                    "created_at": created_at,
                    "tier": unit.tier.value,
                },
            )
            for d in unit.domains:
                conn.execute(q.INSERT_UNIT_DOMAIN, {"unit_id": unit.id, "domain": d})
        # Verify via the orthogonal SqliteStore API.
        assert await store.get_any(unit.id) == unit

    async def test_update_unit_data(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        unit = _make_unit()
        await store.insert(unit)
        new_data = unit.model_copy(
            update={"insight": Insight(summary="updated", detail="d", action="a")}
        ).model_dump_json()
        with engine.begin() as conn:
            conn.execute(
                q.UPDATE_UNIT_DATA,
                {"id": unit.id, "data": new_data, "tier": unit.tier.value},
            )
        retrieved = await store.get_any(unit.id)
        assert retrieved is not None
        assert retrieved.insight.summary == "updated"

    async def test_update_review_status(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        unit = _make_unit()
        await store.insert(unit)
        now = datetime.now(UTC).isoformat()
        with engine.begin() as conn:
            result = conn.execute(
                q.UPDATE_REVIEW_STATUS,
                {"id": unit.id, "status": "approved", "reviewed_by": "rev", "reviewed_at": now},
            )
        assert result.rowcount == 1
        assert await store.get_review_status(unit.id) == {
            "status": "approved",
            "reviewed_by": "rev",
            "reviewed_at": now,
        }

    async def test_update_review_status_missing_returns_zero_rowcount(self, db: tuple[SqliteStore, Engine]) -> None:
        _, engine = db
        with engine.begin() as conn:
            result = conn.execute(
                q.UPDATE_REVIEW_STATUS,
                {
                    "id": "ku_missing",
                    "status": "approved",
                    "reviewed_by": "rev",
                    "reviewed_at": datetime.now(UTC).isoformat(),
                },
            )
        assert result.rowcount == 0

    async def test_delete_unit_domains(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        unit = _make_unit(domains=["a", "b"])
        await store.insert(unit)
        with engine.begin() as conn:
            conn.execute(q.DELETE_UNIT_DOMAINS, {"unit_id": unit.id})
        # No domain rows remain -> domain_counts() is empty for this unit.
        await store.set_review_status(unit.id, "approved", "rev")
        assert await store.domain_counts() == {}

    async def test_insert_unit_duplicate_id_raises(self, db: tuple[SqliteStore, Engine]) -> None:
        """Pins the PRIMARY KEY constraint on knowledge_units.id.

        If a future migration drops this constraint the test fires.
        """
        _, engine = db
        row = {
            "id": "ku_duplicate",
            "data": "{}",
            "created_at": datetime.now(UTC).isoformat(),
            "tier": "private",
        }
        with engine.begin() as conn:
            conn.execute(q.INSERT_UNIT, row)
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(q.INSERT_UNIT, row)


# --- users -----------------------------------------------------------------


class TestUserHelpers:
    async def test_insert_user_and_select(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        created_at = datetime.now(UTC).isoformat()
        with engine.begin() as conn:
            conn.execute(
                q.INSERT_USER,
                {"username": "bob", "password_hash": "hashed", "created_at": created_at},  # pragma: allowlist secret
            )
        user_via_store = await store.get_user("bob")
        assert user_via_store is not None
        with engine.connect() as conn:
            row = conn.execute(q.SELECT_USER_BY_USERNAME, {"username": "bob"}).fetchone()
        assert row is not None
        assert {"id": row[0], "username": row[1], "password_hash": row[2], "created_at": row[3]} == user_via_store

    async def test_insert_user_duplicate_username_raises(self, db: tuple[SqliteStore, Engine]) -> None:
        """Pins the UNIQUE constraint on users.username."""
        _, engine = db
        row = {"username": "duplicate", "password_hash": "h", "created_at": datetime.now(UTC).isoformat()}
        with engine.begin() as conn:
            conn.execute(q.INSERT_USER, row)
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(q.INSERT_USER, row)


# --- api_keys --------------------------------------------------------------


def _api_key_row(*, user_id: int, **overrides: Any) -> dict[str, Any]:
    """Build a row dict suitable for INSERT_API_KEY."""
    now = datetime.now(UTC)
    expires = (now + timedelta(days=90)).isoformat()
    defaults = {
        "id": uuid.uuid4().hex,
        "user_id": user_id,
        "name": "test-key",
        "labels": json.dumps(["production"]),
        "key_prefix": "abcd1234",
        "key_hash": uuid.uuid4().hex,
        "ttl": "90d",
        "expires_at": expires,
        "created_at": now.isoformat(),
    }
    defaults.update(overrides)
    return defaults


class TestApiKeyHelpers:
    async def test_insert_and_count_active(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        user_id = await _seed_user(store)
        row = _api_key_row(user_id=user_id)
        with engine.begin() as conn:
            conn.execute(q.INSERT_API_KEY, row)
        with engine.connect() as conn:
            count = conn.execute(
                q.COUNT_ACTIVE_KEYS_FOR_USER,
                {"user_id": user_id, "now": datetime.now(UTC).isoformat()},
            ).scalar()
        assert count == 1
        assert await store.count_active_api_keys_for_user(user_id) == 1

    async def test_count_active_excludes_expired(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        user_id = await _seed_user(store)
        row = _api_key_row(
            user_id=user_id,
            expires_at=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
        )
        with engine.begin() as conn:
            conn.execute(q.INSERT_API_KEY, row)
        with engine.connect() as conn:
            count = conn.execute(
                q.COUNT_ACTIVE_KEYS_FOR_USER,
                {"user_id": user_id, "now": datetime.now(UTC).isoformat()},
            ).scalar()
        assert count == 0

    async def test_select_key_for_user(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        user_id = await _seed_user(store)
        row = _api_key_row(user_id=user_id)
        with engine.begin() as conn:
            conn.execute(q.INSERT_API_KEY, row)
        with engine.connect() as conn:
            result = conn.execute(
                q.SELECT_KEY_FOR_USER,
                {"key_id": row["id"], "user_id": user_id},
            ).fetchone()
        assert result is not None
        assert result[0] == row["id"]
        assert result[1] == user_id
        # Owner mismatch returns None.
        with engine.connect() as conn:
            other = conn.execute(q.SELECT_KEY_FOR_USER, {"key_id": row["id"], "user_id": user_id + 999}).fetchone()
        assert other is None

    async def test_select_active_key_by_id_joins_username(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        user_id = await _seed_user(store, username="carol")
        row = _api_key_row(user_id=user_id)
        with engine.begin() as conn:
            conn.execute(q.INSERT_API_KEY, row)
        with engine.connect() as conn:
            active = conn.execute(
                q.SELECT_ACTIVE_KEY_BY_ID,
                {"key_id": row["id"], "now": datetime.now(UTC).isoformat()},
            ).fetchone()
        assert active is not None
        assert active[0] == row["id"]
        assert active[2] == "carol"  # username from the JOIN

    async def test_select_active_key_excludes_revoked(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        user_id = await _seed_user(store)
        row = _api_key_row(user_id=user_id)
        with engine.begin() as conn:
            conn.execute(q.INSERT_API_KEY, row)
            conn.execute(
                q.UPDATE_KEY_REVOKE,
                {"key_id": row["id"], "user_id": user_id, "now": datetime.now(UTC).isoformat()},
            )
        with engine.connect() as conn:
            active = conn.execute(
                q.SELECT_ACTIVE_KEY_BY_ID,
                {"key_id": row["id"], "now": datetime.now(UTC).isoformat()},
            ).fetchone()
        assert active is None

    async def test_list_keys_for_user_newest_first(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        user_id = await _seed_user(store)
        older = _api_key_row(user_id=user_id, created_at="2026-01-01T00:00:00+00:00")
        newer = _api_key_row(user_id=user_id, created_at="2026-04-01T00:00:00+00:00")
        with engine.begin() as conn:
            conn.execute(q.INSERT_API_KEY, older)
            conn.execute(q.INSERT_API_KEY, newer)
        with engine.connect() as conn:
            rows = conn.execute(q.LIST_KEYS_FOR_USER, {"user_id": user_id}).fetchall()
        assert [row[0] for row in rows] == [newer["id"], older["id"]]

    async def test_list_keys_isolates_users(self, db: tuple[SqliteStore, Engine]) -> None:
        """Caller's keys only — another user's keys must not appear."""
        store, engine = db
        alice = await _seed_user(store, username="alice")
        bob = await _seed_user(store, username="bob")
        alice_row = _api_key_row(user_id=alice, name="alice-key")
        bob_row = _api_key_row(user_id=bob, name="bob-key")
        with engine.begin() as conn:
            conn.execute(q.INSERT_API_KEY, alice_row)
            conn.execute(q.INSERT_API_KEY, bob_row)
        with engine.connect() as conn:
            alice_rows = conn.execute(q.LIST_KEYS_FOR_USER, {"user_id": alice}).fetchall()
            bob_rows = conn.execute(q.LIST_KEYS_FOR_USER, {"user_id": bob}).fetchall()
        assert [row[0] for row in alice_rows] == [alice_row["id"]]
        assert [row[0] for row in bob_rows] == [bob_row["id"]]

    async def test_update_key_revoke_only_affects_unrevoked(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        user_id = await _seed_user(store)
        row = _api_key_row(user_id=user_id)
        with engine.begin() as conn:
            conn.execute(q.INSERT_API_KEY, row)
            first = conn.execute(
                q.UPDATE_KEY_REVOKE,
                {"key_id": row["id"], "user_id": user_id, "now": datetime.now(UTC).isoformat()},
            )
            second = conn.execute(
                q.UPDATE_KEY_REVOKE,
                {"key_id": row["id"], "user_id": user_id, "now": datetime.now(UTC).isoformat()},
            )
        assert first.rowcount == 1
        assert second.rowcount == 0  # already revoked, idempotent

    async def test_update_key_last_used(self, db: tuple[SqliteStore, Engine]) -> None:
        store, engine = db
        user_id = await _seed_user(store)
        row = _api_key_row(user_id=user_id)
        with engine.begin() as conn:
            conn.execute(q.INSERT_API_KEY, row)
            now = datetime.now(UTC).isoformat()
            conn.execute(q.UPDATE_KEY_LAST_USED, {"key_id": row["id"], "now": now})
        with engine.connect() as conn:
            stored = conn.execute(q.SELECT_KEY_FOR_USER, {"key_id": row["id"], "user_id": user_id}).fetchone()
        assert stored is not None
        assert stored[8] == now  # last_used_at column position
