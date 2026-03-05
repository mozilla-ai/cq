# Tests for knowledge unit data model and confidence scoring.

import pytest

from craic_mcp.knowledge_unit import (
    Context,
    FlagReason,
    Insight,
    KnowledgeUnit,
    Tier,
    create_knowledge_unit,
)
from craic_mcp.scoring import apply_confirmation, apply_flag, calculate_relevance


def _make_insight() -> Insight:
    return Insight(
        summary="Use connection pooling",
        detail="Database connections are expensive to create.",
        action="Configure a connection pool with a max size of 10.",
    )


def _make_unit(**overrides) -> KnowledgeUnit:
    defaults = {
        "domain": ["databases", "performance"],
        "insight": _make_insight(),
    }
    defaults.update(overrides)
    return create_knowledge_unit(**defaults)


class TestKnowledgeUnitCreation:
    def test_auto_generated_id_has_ku_prefix(self):
        unit = _make_unit()
        assert unit.id.startswith("ku_")

    def test_auto_generated_id_has_sufficient_length(self):
        unit = _make_unit()
        # Prefix is 3 chars, nanoid is 21 chars.
        assert len(unit.id) == 24

    def test_default_confidence_is_half(self):
        unit = _make_unit()
        assert unit.evidence.confidence == 0.5

    def test_default_version_is_one(self):
        unit = _make_unit()
        assert unit.version == 1

    def test_default_tier_is_local(self):
        unit = _make_unit()
        assert unit.tier == Tier.LOCAL


class TestApplyConfirmation:
    def test_increases_confidence_by_point_one(self):
        unit = _make_unit()
        confirmed = apply_confirmation(unit)
        assert confirmed.evidence.confidence == pytest.approx(0.6)

    def test_caps_confidence_at_one(self):
        unit = _make_unit()
        # Apply enough confirmations to exceed 1.0.
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
        apply_flag(unit, FlagReason.DUPLICATE)
        assert unit.evidence.confidence == original_confidence


class TestCalculateRelevance:
    def test_exact_domain_match_scores_higher_than_partial(self):
        unit = _make_unit(domain=["databases", "performance"])
        exact_score = calculate_relevance(unit, ["databases", "performance"])
        partial_score = calculate_relevance(unit, ["databases"])
        assert exact_score > partial_score

    def test_no_domain_overlap_gives_zero_domain_component(self):
        unit = _make_unit(domain=["databases"])
        score = calculate_relevance(unit, ["networking"])
        assert score == 0.0

    def test_language_match_adds_secondary_signal(self):
        unit = _make_unit(
            context=Context(languages=["python"], frameworks=[])
        )
        score_with_lang = calculate_relevance(
            unit, ["databases"], query_language="python"
        )
        score_without_lang = calculate_relevance(
            unit, ["databases"], query_language=None
        )
        assert score_with_lang > score_without_lang

    def test_framework_match_adds_secondary_signal(self):
        unit = _make_unit(
            context=Context(languages=[], frameworks=["django"])
        )
        score_with_fw = calculate_relevance(
            unit, ["databases"], query_framework="django"
        )
        score_without_fw = calculate_relevance(
            unit, ["databases"], query_framework=None
        )
        assert score_with_fw > score_without_fw

    def test_full_match_returns_one(self):
        unit = _make_unit(
            domain=["databases"],
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
            domain=["databases", "performance"],
            context=Context(languages=["python"], frameworks=["django"]),
        )
        score = calculate_relevance(
            unit,
            ["databases", "caching"],
            query_language="python",
            query_framework="flask",
        )
        assert 0.0 <= score <= 1.0


class TestSerializationRoundTrip:
    def test_model_dump_and_validate_roundtrip(self):
        unit = _make_unit()
        data = unit.model_dump()
        restored = KnowledgeUnit.model_validate(data)
        assert restored == unit

    def test_json_roundtrip(self):
        unit = _make_unit()
        json_str = unit.model_dump_json()
        restored = KnowledgeUnit.model_validate_json(json_str)
        assert restored == unit
