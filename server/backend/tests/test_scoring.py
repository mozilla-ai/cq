"""Tests for confidence scoring and relevance functions."""

from typing import Any

from cq.models import Context, Insight, KnowledgeUnit, create_knowledge_unit

from cq_server.scoring import calculate_relevance


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


class TestServerPatternBoost:
    def test_matching_pattern_boosts(self):
        unit = _make_unit(domains=["api"], context=Context(pattern="api-client"))
        with_p = calculate_relevance(unit, ["api"], query_pattern="api-client")
        without = calculate_relevance(unit, ["api"])
        assert with_p > without
        assert abs((without + 0.15) - with_p) < 1e-9

    def test_non_matching_pattern_no_boost(self):
        unit = _make_unit(domains=["api"], context=Context(pattern="api-client"))
        with_p = calculate_relevance(unit, ["api"], query_pattern="cli-tool")
        without = calculate_relevance(unit, ["api"])
        assert with_p == without

    def test_pattern_case_insensitive(self):
        unit = _make_unit(domains=["api"], context=Context(pattern="api-client"))
        upper = calculate_relevance(unit, ["api"], query_pattern="API-Client")
        lower = calculate_relevance(unit, ["api"], query_pattern="api-client")
        assert upper == lower

    def test_empty_stored_pattern_never_matches(self):
        unit = _make_unit(domains=["api"])
        score = calculate_relevance(unit, ["api"], query_pattern="any")
        baseline = calculate_relevance(unit, ["api"])
        assert score == baseline

    def test_all_signals_match_reaches_one(self):
        unit = _make_unit(
            domains=["api"],
            context=Context(languages=["python"], frameworks=["fastapi"], pattern="api-client"),
        )
        score = calculate_relevance(
            unit,
            ["api"],
            query_languages=["python"],
            query_frameworks=["fastapi"],
            query_pattern="api-client",
        )
        assert abs(score - 1.0) < 1e-9
