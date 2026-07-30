"""Tests for knowledge unit data models and serialization."""

import json
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from cq_schema import (
    ACTION_MAX_LENGTH,
    CREATED_BY_MAX_LENGTH,
    DETAIL_MAX_LENGTH,
    DOMAIN_MAX_LENGTH,
    DOMAINS_MAX_ITEMS,
    FLAG_DETAIL_MAX_LENGTH,
    FRAMEWORK_MAX_LENGTH,
    FRAMEWORKS_MAX_ITEMS,
    LANGUAGE_MAX_LENGTH,
    LANGUAGES_MAX_ITEMS,
    PATTERN_MAX_LENGTH,
    SUMMARY_MAX_LENGTH,
)
from pydantic import ValidationError

from cq.models import (
    Context,
    Evidence,
    Flag,
    FlagReason,
    Insight,
    KnowledgeUnit,
    Tier,
    create_knowledge_unit,
)


def _make_insight() -> Insight:
    return Insight(
        summary="Use connection pooling",
        detail="Database connections are expensive to create.",
        action="Configure a connection pool with a max size of 10.",
    )


def _make_unit(**overrides: object) -> KnowledgeUnit:
    defaults = {
        "domains": ["databases", "performance"],
        "insight": _make_insight(),
    }
    defaults.update(overrides)
    return create_knowledge_unit(**defaults)


# The first element is the field token the actionable error message must name; it drives both the
# accept/reject enforcement tests and the error-message content test, so every constrained string is
# covered once. List-item fields carry the list's plural name because that is what the message reports.
_LENGTH_CASES = [
    ("summary", SUMMARY_MAX_LENGTH, lambda v: Insight(summary=v, detail="d", action="a")),
    ("detail", DETAIL_MAX_LENGTH, lambda v: Insight(summary="s", detail=v, action="a")),
    ("action", ACTION_MAX_LENGTH, lambda v: Insight(summary="s", detail="d", action=v)),
    ("pattern", PATTERN_MAX_LENGTH, lambda v: Context(pattern=v)),
    ("languages", LANGUAGE_MAX_LENGTH, lambda v: Context(languages=[v])),
    ("frameworks", FRAMEWORK_MAX_LENGTH, lambda v: Context(frameworks=[v])),
    ("domains", DOMAIN_MAX_LENGTH, lambda v: _make_unit(domains=[v])),
    ("created_by", CREATED_BY_MAX_LENGTH, lambda v: _make_unit(created_by=v)),
    ("detail", FLAG_DETAIL_MAX_LENGTH, lambda v: Flag(reason=FlagReason.STALE, detail=v)),
]

_ITEMS_CASES = [
    ("domains", DOMAINS_MAX_ITEMS, lambda n: _make_unit(domains=["d"] * n)),
    ("languages", LANGUAGES_MAX_ITEMS, lambda n: Context(languages=["l"] * n)),
    ("frameworks", FRAMEWORKS_MAX_ITEMS, lambda n: Context(frameworks=["f"] * n)),
]


class TestKnowledgeUnitCreation:
    def test_auto_generated_id_has_ku_prefix(self) -> None:
        unit = _make_unit()
        assert unit.id.startswith("ku_")

    def test_auto_generated_id_has_sufficient_length(self) -> None:
        unit = _make_unit()
        # Prefix is 3 chars, UUID hex is 32 chars.
        assert len(unit.id) == 35

    def test_default_confidence_is_half(self) -> None:
        unit = _make_unit()
        assert unit.evidence.confidence == 0.5

    def test_default_version_is_one(self) -> None:
        unit = _make_unit()
        assert unit.version == 1

    def test_default_tier_is_local(self) -> None:
        unit = _make_unit()
        assert unit.tier == Tier.LOCAL


class TestEvidenceTimestamps:
    def test_timestamps_are_identical_on_creation(self) -> None:
        evidence = Evidence()
        assert evidence.first_observed == evidence.last_confirmed

    def test_explicit_timestamps_are_preserved(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=UTC)
        evidence = Evidence(first_observed=ts, last_confirmed=ts)
        assert evidence.first_observed == ts
        assert evidence.last_confirmed == ts

    def test_only_first_observed_copies_to_last_confirmed(self) -> None:
        ts = datetime(2025, 6, 15, tzinfo=UTC)
        evidence = Evidence(first_observed=ts)
        assert evidence.last_confirmed == ts

    def test_only_last_confirmed_copies_to_first_observed(self) -> None:
        ts = datetime(2025, 6, 15, tzinfo=UTC)
        evidence = Evidence(last_confirmed=ts)
        assert evidence.first_observed == ts


class TestConfidenceBounds:
    def test_rejects_confidence_above_one(self) -> None:
        with pytest.raises(ValidationError):
            Evidence(confidence=5.0)

    def test_rejects_confidence_below_zero(self) -> None:
        with pytest.raises(ValidationError):
            Evidence(confidence=-0.1)

    def test_accepts_boundary_values(self) -> None:
        low = Evidence(confidence=0.0)
        high = Evidence(confidence=1.0)
        assert low.confidence == 0.0
        assert high.confidence == 1.0


class TestDomainValidation:
    def test_rejects_empty_domain_list(self) -> None:
        with pytest.raises(ValidationError):
            KnowledgeUnit(
                id="ku_00000000000000000000000000000001",
                domains=[],
                insight=_make_insight(),
            )

    def test_accepts_single_domain(self) -> None:
        unit = KnowledgeUnit(
            id="ku_00000000000000000000000000000001",
            domains=["databases"],
            insight=_make_insight(),
        )
        assert unit.domains == ["databases"]


class TestCreateKnowledgeUnitCoercion:
    def test_bare_string_domains_coerced_to_list(self) -> None:
        unit = create_knowledge_unit(
            domains="api",  # type: ignore[arg-type]
            insight=_make_insight(),
        )
        assert unit.domains == ["api"]


class TestIdUniqueness:
    def test_two_units_have_different_ids(self) -> None:
        unit_a = _make_unit()
        unit_b = _make_unit()
        assert unit_a.id != unit_b.id


class TestSerializationRoundTrip:
    def test_model_dump_and_validate_roundtrip(self) -> None:
        unit = _make_unit()
        data = unit.model_dump()
        restored = KnowledgeUnit.model_validate(data)
        assert restored == unit

    def test_json_roundtrip(self) -> None:
        unit = _make_unit()
        json_str = unit.model_dump_json()
        restored = KnowledgeUnit.model_validate_json(json_str)
        assert restored == unit


class TestWireFormat:
    """Pin the exact JSON wire format for cross-language compatibility.

    The local SQLite DB stores knowledge units as JSON blobs. Both the
    Go and Python SDKs must read and write the same format. These tests
    ensure a refactor never silently changes the serialized enum values
    or field names, which would corrupt the shared database.
    """

    def test_tier_serializes_to_clean_value_in_json(self) -> None:
        unit = _make_unit()
        data = json.loads(unit.model_dump_json())
        assert data["tier"] == "local"

    def test_all_tiers_serialize_to_clean_values(self) -> None:
        for tier, expected in [
            (Tier.LOCAL, "local"),
            (Tier.PRIVATE, "private"),
            (Tier.PUBLIC, "public"),
        ]:
            unit = _make_unit(tier=tier)
            data = json.loads(unit.model_dump_json())
            assert data["tier"] == expected

    def test_flag_reason_serializes_to_clean_value_in_json(self) -> None:
        flag = Flag(reason=FlagReason.STALE)
        data = json.loads(flag.model_dump_json())
        assert data["reason"] == "stale"

    def test_all_flag_reasons_serialize_to_clean_values(self) -> None:
        for reason, expected in [
            (FlagReason.STALE, "stale"),
            (FlagReason.INCORRECT, "incorrect"),
            (FlagReason.DUPLICATE, "duplicate"),
        ]:
            kwargs: dict = {"reason": reason}
            if reason is FlagReason.DUPLICATE:
                kwargs["duplicate_of"] = "ku_00000000000000000000000000000001"
            flag = Flag(**kwargs)
            data = json.loads(flag.model_dump_json())
            assert data["reason"] == expected

    def test_tier_deserializes_from_clean_value(self) -> None:
        unit = _make_unit()
        raw = unit.model_dump_json()
        raw = raw.replace('"local"', '"private"')
        restored = KnowledgeUnit.model_validate_json(raw)
        assert restored.tier == Tier.PRIVATE

    def test_flag_reason_deserializes_from_clean_value(self) -> None:
        flag = Flag(reason=FlagReason.STALE)
        raw = flag.model_dump_json()
        raw = raw.replace('"stale"', '"incorrect"')
        restored = Flag.model_validate_json(raw)
        assert restored.reason == FlagReason.INCORRECT

    def test_json_field_names(self) -> None:
        unit = _make_unit(
            context=Context(languages=["python"], frameworks=["django"], pattern="web"),
        )
        data = json.loads(unit.model_dump_json())
        assert "id" in data
        assert "version" in data
        assert "domains" in data
        assert "insight" in data
        assert "context" in data
        assert "evidence" in data
        assert "tier" in data
        assert "created_by" in data
        assert "superseded_by" in data
        assert "flags" in data
        # Nested field names.
        assert "summary" in data["insight"]
        assert "detail" in data["insight"]
        assert "action" in data["insight"]
        assert "languages" in data["context"]
        assert "frameworks" in data["context"]
        assert "pattern" in data["context"]
        assert "confidence" in data["evidence"]
        assert "confirmations" in data["evidence"]
        assert "first_observed" in data["evidence"]
        assert "last_confirmed" in data["evidence"]


class TestFlagModel:
    def test_flag_has_timestamp(self) -> None:
        flag = Flag(reason=FlagReason.STALE)
        assert flag.timestamp is not None

    def test_flag_reason_values(self) -> None:
        assert FlagReason.STALE == "stale"
        assert FlagReason.INCORRECT == "incorrect"
        assert FlagReason.DUPLICATE == "duplicate"


class TestExtensionKeyValidation:
    @pytest.mark.parametrize(
        "key",
        [
            "impl:key",
            "cq:severity",
            "my-impl:nested-key",
            "a:b",
            "abc_def:ghi",
            "tool123:config",
            "impl:key.with.dots",
            "ns:UPPER-value",
        ],
    )
    def test_accepts_valid_extension_keys(self, key: str) -> None:
        unit = _make_unit(extensions={key: "v"})
        assert key in unit.extensions

    @pytest.mark.parametrize(
        "key",
        [
            "no-namespace",
            ":missing-slug",
            "MixedCase:key",
            "",
            "UPPER:key",
            "-starts-with-dash:key",
            "_starts-with-underscore:key",
            "impl:",
            " space:key",
            "impl: space-value",
            "impl:has space",
            "impl:\ttab-value",
            "impl: ",
        ],
    )
    def test_rejects_invalid_extension_keys(self, key: str) -> None:
        with pytest.raises(ValidationError):
            _make_unit(extensions={key: "v"})

    def test_accepts_none_extensions(self) -> None:
        unit = _make_unit()
        assert unit.extensions is None

    def test_accepts_empty_extensions(self) -> None:
        unit = _make_unit(extensions={})
        assert unit.extensions == {}


class TestTierEnum:
    def test_tier_values(self) -> None:
        assert Tier.LOCAL == "local"
        assert Tier.PRIVATE == "private"
        assert Tier.PUBLIC == "public"


class TestFieldLimits:
    @pytest.mark.parametrize(("field", "limit", "build"), _LENGTH_CASES)
    def test_accepts_at_max_length(self, field: str, limit: int, build: Callable[[str], object]) -> None:
        build("x" * limit)

    @pytest.mark.parametrize(("field", "limit", "build"), _LENGTH_CASES)
    def test_rejects_over_max_length(self, field: str, limit: int, build: Callable[[str], object]) -> None:
        with pytest.raises(ValidationError):
            build("x" * (limit + 1))

    @pytest.mark.parametrize(("field", "limit", "build"), _ITEMS_CASES)
    def test_accepts_at_max_items(self, field: str, limit: int, build: Callable[[int], object]) -> None:
        build(limit)

    @pytest.mark.parametrize(("field", "limit", "build"), _ITEMS_CASES)
    def test_rejects_over_max_items(self, field: str, limit: int, build: Callable[[int], object]) -> None:
        with pytest.raises(ValidationError):
            build(limit + 1)

    @pytest.mark.parametrize(("field", "limit", "build"), _LENGTH_CASES)
    def test_error_message_names_field_limit_and_length(
        self, field: str, limit: int, build: Callable[[str], object]
    ) -> None:
        over = limit + 1
        with pytest.raises(ValidationError) as exc:
            build("x" * over)
        message = str(exc.value)
        assert field in message
        assert str(limit) in message
        assert str(over) in message
