"""Behavior tests for the repository layer running on PostgreSQL.

These exercise the queries that diverge between SQLite and PostgreSQL
(confidence distribution, daily counts) plus a basic round-trip smoke
test, all against the session-scoped ``pg_repos`` fixture (a real
PostgreSQL container). The whole module skips when Docker is unavailable.
"""

from datetime import UTC, datetime
from typing import Any

from cq.models import Evidence, Insight, KnowledgeUnit, create_knowledge_unit

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


async def _insert_and_approve(repos: _RepoBundle, **kwargs: Any) -> KnowledgeUnit:
    unit = _make_unit(**kwargs)
    await repos.insert(unit)
    await repos.set_review_status(unit.id, "approved", "reviewer")
    return unit


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
