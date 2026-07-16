"""Behavior tests for the repository layer running on PostgreSQL.

These exercise the queries that diverge between SQLite and PostgreSQL
(confidence distribution, daily counts) plus a basic round-trip smoke
test, all against the ``pg_repos`` fixture (function-scoped repositories
sharing the session-scoped ``pg_url`` PostgreSQL container). The whole
module skips when Docker is unavailable.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from cq.models import Evidence, Insight, KnowledgeUnit, create_knowledge_unit
from sqlalchemy import text

from cq_server.repositories._queries import SELECT_PROPOSED_DAILY

from .db_helpers import _RepoBundle


def _make_unit(*, confidence: float = 0.9, **overrides: Any) -> KnowledgeUnit:
    defaults: dict[str, Any] = {
        "domains": ["databases", "performance"],
        "insight": Insight(
            summary="Use connection pooling",
            detail="Database connections are expensive to create.",
            action="Configure a connection pool with a max size of 10.",
        ),
    }
    unit = create_knowledge_unit(**{**defaults, **overrides})
    unit.evidence = Evidence(confidence=confidence)
    return unit


async def _insert_and_review(repos: _RepoBundle, status: str, **kwargs: Any) -> KnowledgeUnit:
    unit = _make_unit(**kwargs)
    await repos.insert(unit)
    await repos.set_review_status(unit.id, status, "reviewer")
    return unit


async def _insert_and_approve(repos: _RepoBundle, **kwargs: Any) -> KnowledgeUnit:
    return await _insert_and_review(repos, "approved", **kwargs)


async def test_pg_insert_query_roundtrip(pg_repos: _RepoBundle) -> None:
    unit = await _insert_and_approve(pg_repos, domains=["databases"])
    results = await pg_repos.query(["databases"])
    assert [u.id for u in results] == [unit.id]


async def test_pg_knowledge_confidence_distribution(pg_repos: _RepoBundle) -> None:
    # Buckets: 0.0-0.3, 0.3-0.5, 0.5-0.7, 0.7-1.0
    await _insert_and_approve(pg_repos, confidence=0.2)
    await _insert_and_approve(pg_repos, confidence=0.6)
    await _insert_and_approve(pg_repos, confidence=0.95)
    dist = await pg_repos.knowledge.confidence_distribution()
    assert dist == {"0.0-0.3": 1, "0.3-0.5": 0, "0.5-0.7": 1, "0.7-1.0": 1}


async def test_pg_reviews_confidence_distribution(pg_repos: _RepoBundle) -> None:
    # Review dashboard buckets: 0.0-0.3, 0.3-0.6, 0.6-0.8, 0.8-1.0
    await _insert_and_approve(pg_repos, confidence=0.2)
    await _insert_and_approve(pg_repos, confidence=0.5)
    await _insert_and_approve(pg_repos, confidence=0.9)
    dist = await pg_repos.reviews.confidence_distribution()
    assert dist == {"0.0-0.3": 1, "0.3-0.6": 1, "0.6-0.8": 0, "0.8-1.0": 1}


async def test_pg_daily_counts(pg_repos: _RepoBundle) -> None:
    # One proposed+approved unit today; daily_counts must aggregate it by day
    # via ``to_char(created_at::timestamptz, 'YYYY-MM-DD')``, not ``date(text)``.
    await _insert_and_approve(pg_repos)
    rows = await pg_repos.daily_counts(days=7)
    today = datetime.now(UTC).date().isoformat()
    by_date = {r["date"]: r for r in rows}
    assert by_date[today]["proposed"] == 1
    assert by_date[today]["approved"] == 1


async def test_pg_daily_counts_rejected(pg_repos: _RepoBundle) -> None:
    # The rejected-daily query is a distinct dialect-keyed branch; cover it too.
    await _insert_and_review(pg_repos, "rejected")
    rows = await pg_repos.daily_counts(days=7)
    today = datetime.now(UTC).date().isoformat()
    by_date = {r["date"]: r for r in rows}
    assert by_date[today]["rejected"] == 1
    assert by_date[today]["approved"] == 0


async def test_pg_daily_counts_excludes_before_cutoff(pg_repos: _RepoBundle) -> None:
    # The ``>= :cutoff`` filter is copy-pasted into the PG variant of ``_daily``
    # (not shared with the SQLite one), and on PG it is a lexicographic text
    # comparison against the TEXT column. Pin it directly: a row dated exactly
    # on the cutoff is included, one a second before is excluded.
    now = datetime.now(UTC)
    cutoff_date = (now - timedelta(days=30)).date()
    midnight = datetime(cutoff_date.year, cutoff_date.month, cutoff_date.day, tzinfo=UTC)
    on_cutoff = await _insert_and_approve(pg_repos, domains=["on"])
    before_cutoff = await _insert_and_approve(pg_repos, domains=["before"])
    with pg_repos._engine.begin() as conn:
        update = text("UPDATE knowledge_units SET created_at = :when WHERE id = :id")
        conn.execute(update, {"when": midnight.isoformat(), "id": on_cutoff.id})
        conn.execute(update, {"when": (midnight - timedelta(seconds=1)).isoformat(), "id": before_cutoff.id})
    with pg_repos._engine.connect() as conn:
        rows = conn.execute(SELECT_PROPOSED_DAILY["postgresql"], {"cutoff": cutoff_date.isoformat()}).fetchall()
    counts = {row[0]: row[1] for row in rows}
    assert counts.get(cutoff_date.isoformat()) == 1  # on-cutoff row included
    assert sum(counts.values()) == 1  # before-cutoff row excluded entirely


async def test_pg_daily_counts_datestyle_independent(pg_repos: _RepoBundle) -> None:
    # The day key uses ``to_char(..., 'YYYY-MM-DD')`` rather than ``::date::text``
    # precisely so it stays ISO regardless of the session ``DateStyle``. Run the
    # proposed-daily query on a connection pinned to a non-ISO DateStyle and
    # assert the key is still ISO — a regression to ``::date::text`` would yield
    # e.g. '16.07.2026' and fail here.
    await _insert_and_approve(pg_repos)
    cutoff = (datetime.now(UTC) - timedelta(days=7)).date().isoformat()
    with pg_repos._engine.connect() as conn:
        conn.execute(text("SET DateStyle = 'German, DMY'"))
        rows = conn.execute(SELECT_PROPOSED_DAILY["postgresql"], {"cutoff": cutoff}).fetchall()
    today = datetime.now(UTC).date().isoformat()
    assert today in {row[0] for row in rows}
