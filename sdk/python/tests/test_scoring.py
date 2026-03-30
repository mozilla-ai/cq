"""Tests for confidence scoring and relevance functions."""

import pytest

from cq.models import Context, FlagReason, Insight, create_knowledge_unit
from cq.scoring import apply_confirmation, apply_flag, calculate_relevance


def _make_unit(**overrides):
    defaults = {
        "domains": ["databases", "performance"],
        "insight": Insight(
            summary="Use connection pooling",
            detail="Database connections are expensive to create.",
            action="Configure a connection pool with a max size of 10.",
        ),
    }
    defaults.update(overrides)
    return create_knowledge_unit(**defaults)


class TestApplyConfirmation:
    def test_increases_confidence_by_point_one(self):
        unit = _make_unit()
        confirmed = apply_confirmation(unit)
        assert confirmed.evidence.confidence == pytest.approx(0.6)

    def test_caps_confidence_at_one(self):
        unit = _make_unit()
        for _ in range(10):
            unit = apply_confirmation(unit)
        assert unit.evidence.confidence == 1.0

    def test_increments_confirmations_count(self):
        unit = _make_unit()
        assert unit.evidence.confirmations == 1
        confirmed = apply_confirmation(unit)
        assert confirmed.evidence.confirmations == 2

    def test_updates_last_confirmed_timestamp(self):
        unit = _make_unit()
        original_timestamp = unit.evidence.last_confirmed
        confirmed = apply_confirmation(unit)
        assert confirmed.evidence.last_confirmed >= original_timestamp

    def test_does_not_mutate_original(self):
        unit = _make_unit()
        original_confidence = unit.evidence.confidence
        apply_confirmation(unit)
        assert unit.evidence.confidence == original_confidence


class TestApplyFlag:
    def test_decreases_confidence_by_point_one_five(self):
        unit = _make_unit()
        flagged = apply_flag(unit, FlagReason.STALE)
        assert flagged.evidence.confidence == pytest.approx(0.35)

    def test_floors_confidence_at_zero(self):
        unit = _make_unit()
        for _ in range(10):
            unit = apply_flag(unit, FlagReason.INCORRECT)
        assert unit.evidence.confidence == 0.0

    def test_does_not_mutate_original(self):
        unit = _make_unit()
        original_confidence = unit.evidence.confidence
        apply_flag(unit, FlagReason.DUPLICATE, duplicate_of="ku_00000000000000000000000000000001")
        assert unit.evidence.confidence == original_confidence

    def test_records_single_flag(self):
        unit = _make_unit()
        flagged = apply_flag(unit, FlagReason.STALE)
        assert len(flagged.flags) == 1
        assert flagged.flags[0].reason == FlagReason.STALE

    def test_records_multiple_flags(self):
        unit = _make_unit()
        unit = apply_flag(unit, FlagReason.STALE)
        unit = apply_flag(unit, FlagReason.INCORRECT)
        assert len(unit.flags) == 2
        assert unit.flags[0].reason == FlagReason.STALE
        assert unit.flags[1].reason == FlagReason.INCORRECT

    def test_flag_has_timestamp(self):
        unit = _make_unit()
        flagged = apply_flag(unit, FlagReason.DUPLICATE, duplicate_of="ku_00000000000000000000000000000001")
        assert flagged.flags[0].timestamp is not None

    def test_original_unit_has_no_flags(self):
        unit = _make_unit()
        apply_flag(unit, FlagReason.STALE)
        assert len(unit.flags) == 0


class TestCalculateRelevance:
    def test_exact_domain_match_scores_higher_than_partial(self):
        unit = _make_unit(domains=["databases", "performance"])
        exact_score = calculate_relevance(unit, ["databases", "performance"])
        partial_score = calculate_relevance(unit, ["databases"])
        assert exact_score > partial_score

    def test_no_domain_overlap_gives_zero(self):
        unit = _make_unit(domains=["databases"])
        score = calculate_relevance(unit, ["networking"])
        assert score == 0.0

    def test_language_match_adds_secondary_signal(self):
        unit = _make_unit(context=Context(languages=["python"], frameworks=[]))
        score_with_lang = calculate_relevance(unit, ["databases"], query_language="python")
        score_without_lang = calculate_relevance(unit, ["databases"], query_language=None)
        assert score_with_lang > score_without_lang

    def test_framework_match_adds_secondary_signal(self):
        unit = _make_unit(context=Context(languages=[], frameworks=["django"]))
        score_with_fw = calculate_relevance(unit, ["databases"], query_framework="django")
        score_without_fw = calculate_relevance(unit, ["databases"], query_framework=None)
        assert score_with_fw > score_without_fw

    def test_full_match_returns_one(self):
        unit = _make_unit(
            domains=["databases"],
            context=Context(languages=["python"], frameworks=["django"]),
        )
        score = calculate_relevance(
            unit,
            ["databases"],
            query_language="python",
            query_framework="django",
        )
        assert score == pytest.approx(1.0)

    def test_relevance_is_between_zero_and_one(self):
        unit = _make_unit(
            domains=["databases", "performance"],
            context=Context(languages=["python"], frameworks=["django"]),
        )
        score = calculate_relevance(
            unit,
            ["databases", "caching"],
            query_language="python",
            query_framework="flask",
        )
        assert 0.0 <= score <= 1.0
