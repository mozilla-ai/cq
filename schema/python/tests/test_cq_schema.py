"""Tests for the cq_schema package."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import jsonschema
import pytest

import cq_schema

SCHEMA_NAMES = [
    "confirm",
    "flag",
    "health",
    "knowledge_unit",
    "propose",
    "query",
    "review",
    "scoring",
    "stats",
]


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_load_schema_returns_valid_json_with_draft_2020_12(name: str) -> None:
    schema = cq_schema.load_schema(name)
    assert isinstance(schema, dict)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_load_schema_bytes_matches_load_schema(name: str) -> None:
    raw = cq_schema.load_schema_bytes(name)
    parsed = cq_schema.load_schema(name)
    assert json.loads(raw) == parsed


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_bundled_schema_matches_canonical(name: str) -> None:
    canonical = Path(__file__).resolve().parent.parent.parent / f"{name}.json"
    assert cq_schema.load_schema(name) == json.loads(canonical.read_text(encoding="utf-8"))


def test_load_schema_missing_raises() -> None:
    with pytest.raises(FileNotFoundError):
        cq_schema.load_schema("does_not_exist")


def test_scoring_constants_match_values_file() -> None:
    raw = cq_schema.load_schema_bytes("scoring.values")
    values = json.loads(raw)
    relevance = values["relevance_weights"]
    confidence = values["confidence_constants"]

    assert relevance["domain_weight"] == cq_schema.DOMAIN_WEIGHT
    assert relevance["language_weight"] == cq_schema.LANGUAGE_WEIGHT
    assert relevance["framework_weight"] == cq_schema.FRAMEWORK_WEIGHT
    assert relevance["pattern_weight"] == cq_schema.PATTERN_WEIGHT

    assert confidence["initial_confidence"] == cq_schema.INITIAL_CONFIDENCE
    assert confidence["confirmation_boost"] == cq_schema.CONFIRMATION_BOOST
    assert confidence["flag_penalty"] == cq_schema.FLAG_PENALTY
    assert confidence["ceiling"] == cq_schema.CONFIDENCE_CEILING
    assert confidence["floor"] == cq_schema.CONFIDENCE_FLOOR


def test_schema_limits_match_schema() -> None:
    schema = cq_schema.load_schema("knowledge_unit")
    properties = schema["properties"]
    defs = schema["$defs"]
    insight = defs["Insight"]["properties"]
    context = defs["Context"]["properties"]
    flag = defs["Flag"]["properties"]

    assert insight["summary"]["maxLength"] == cq_schema.SUMMARY_MAX_LENGTH
    assert insight["detail"]["maxLength"] == cq_schema.DETAIL_MAX_LENGTH
    assert insight["action"]["maxLength"] == cq_schema.ACTION_MAX_LENGTH
    assert properties["domains"]["items"]["maxLength"] == cq_schema.DOMAIN_MAX_LENGTH
    assert properties["created_by"]["maxLength"] == cq_schema.CREATED_BY_MAX_LENGTH
    assert context["pattern"]["maxLength"] == cq_schema.PATTERN_MAX_LENGTH
    assert context["languages"]["items"]["maxLength"] == cq_schema.LANGUAGE_MAX_LENGTH
    assert context["frameworks"]["items"]["maxLength"] == cq_schema.FRAMEWORK_MAX_LENGTH
    assert flag["detail"]["maxLength"] == cq_schema.FLAG_DETAIL_MAX_LENGTH
    assert properties["domains"]["maxItems"] == cq_schema.DOMAINS_MAX_ITEMS
    assert context["languages"]["maxItems"] == cq_schema.LANGUAGES_MAX_ITEMS
    assert context["frameworks"]["maxItems"] == cq_schema.FRAMEWORKS_MAX_ITEMS


def test_request_schemas_mirror_knowledge_unit_bounds() -> None:
    ku = cq_schema.load_schema("knowledge_unit")
    ku_props = ku["properties"]
    ku_context = ku["$defs"]["Context"]["properties"]
    ku_flag = ku["$defs"]["Flag"]["properties"]

    for schema_name in ("propose", "query"):
        domains = cq_schema.load_schema(schema_name)["properties"]["domains"]
        assert domains["items"]["maxLength"] == ku_props["domains"]["items"]["maxLength"]
        assert domains["maxItems"] == ku_props["domains"]["maxItems"]

    propose = cq_schema.load_schema("propose")
    assert propose["properties"]["created_by"]["maxLength"] == ku_props["created_by"]["maxLength"]

    query = cq_schema.load_schema("query")
    for field in ("languages", "frameworks"):
        assert query["properties"][field]["items"]["maxLength"] == ku_context[field]["items"]["maxLength"]
        assert query["properties"][field]["maxItems"] == ku_context[field]["maxItems"]

    flag = cq_schema.load_schema("flag")
    assert flag["properties"]["detail"]["maxLength"] == ku_flag["detail"]["maxLength"]


def test_scoring_values_validates_against_scoring_schema() -> None:
    schema = cq_schema.load_schema("scoring")
    values = json.loads(cq_schema.load_schema_bytes("scoring.values"))
    jsonschema.validate(instance=values, schema=schema)


def test_knowledge_unit_fixtures_validate() -> None:
    schema = cq_schema.load_schema("knowledge_unit")
    fixtures_dir = Path(__file__).resolve().parent.parent.parent / "fixtures"
    for fixture_name in (
        "valid-unit.json",
        "minimal-unit.json",
        "flagged-unit.json",
        "duplicate-flag.json",
        "extensions-unit.json",
    ):
        instance = json.loads((fixtures_dir / fixture_name).read_text(encoding="utf-8"))
        jsonschema.validate(instance=instance, schema=schema)


@pytest.mark.parametrize(
    "bad_key",
    [
        "no-namespace",
        ":missing-slug",
        "MixedCase:key",
        "",
        "impl: space-value",
        "impl:has space",
        "impl:\ttab-value",
        "impl: ",
    ],
)
def test_extensions_reject_unnamespaced_keys(bad_key: str) -> None:
    schema = cq_schema.load_schema("knowledge_unit")
    instance = {
        "id": "ku_00000000000000000000000000000099",
        "domains": ["test"],
        "insight": {"summary": "s", "detail": "d", "action": "a"},
        "extensions": {bad_key: "value"},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=instance, schema=schema)


def test_extensions_reject_more_than_twenty_keys() -> None:
    schema = cq_schema.load_schema("knowledge_unit")
    instance = {
        "id": "ku_00000000000000000000000000000099",
        "domains": ["test"],
        "insight": {"summary": "s", "detail": "d", "action": "a"},
        "extensions": {f"ns:key{i}": i for i in range(21)},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=instance, schema=schema)


def test_extensions_accept_namespaced_keys() -> None:
    schema = cq_schema.load_schema("knowledge_unit")
    instance = {
        "id": "ku_00000000000000000000000000000099",
        "domains": ["test"],
        "insight": {"summary": "s", "detail": "d", "action": "a"},
        "extensions": {
            "impl:key": "string-value",
            "my-impl:nested": {"a": 1},
            "x0:flag": True,
        },
    }
    jsonschema.validate(instance=instance, schema=schema)


_VALID_ID = "ku_00000000000000000000000000000099"


def _unit(**fields: object) -> dict[str, object]:
    instance: dict[str, object] = {
        "id": _VALID_ID,
        "domains": ["d"],
        "insight": {"summary": "s", "detail": "d", "action": "a"},
    }
    instance.update(fields)
    return instance


def _unit_with_summary(value: str) -> dict[str, object]:
    return _unit(insight={"summary": value, "detail": "d", "action": "a"})


def _unit_with_detail(value: str) -> dict[str, object]:
    return _unit(insight={"summary": "s", "detail": value, "action": "a"})


def _unit_with_action(value: str) -> dict[str, object]:
    return _unit(insight={"summary": "s", "detail": "d", "action": value})


def _unit_with_domain(value: str) -> dict[str, object]:
    return _unit(domains=[value])


def _unit_with_created_by(value: str) -> dict[str, object]:
    return _unit(created_by=value)


def _unit_with_pattern(value: str) -> dict[str, object]:
    return _unit(context={"pattern": value})


def _unit_with_language(value: str) -> dict[str, object]:
    return _unit(context={"languages": [value]})


def _unit_with_framework(value: str) -> dict[str, object]:
    return _unit(context={"frameworks": [value]})


def _unit_with_flag_detail(value: str) -> dict[str, object]:
    return _unit(flags=[{"reason": "stale", "detail": value}])


@pytest.mark.parametrize(
    ("limit_name", "build"),
    [
        ("SUMMARY_MAX_LENGTH", _unit_with_summary),
        ("DETAIL_MAX_LENGTH", _unit_with_detail),
        ("ACTION_MAX_LENGTH", _unit_with_action),
        ("DOMAIN_MAX_LENGTH", _unit_with_domain),
        ("CREATED_BY_MAX_LENGTH", _unit_with_created_by),
        ("PATTERN_MAX_LENGTH", _unit_with_pattern),
        ("LANGUAGE_MAX_LENGTH", _unit_with_language),
        ("FRAMEWORK_MAX_LENGTH", _unit_with_framework),
        ("FLAG_DETAIL_MAX_LENGTH", _unit_with_flag_detail),
    ],
)
def test_free_text_field_enforces_max_length(limit_name: str, build: Callable[[str], dict[str, object]]) -> None:
    schema = cq_schema.load_schema("knowledge_unit")
    limit = getattr(cq_schema, limit_name)

    jsonschema.validate(instance=build("x" * limit), schema=schema)

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=build("x" * (limit + 1)), schema=schema)


def _unit_with_domains(count: int) -> dict[str, object]:
    return _unit(domains=["d"] * count)


def _unit_with_languages(count: int) -> dict[str, object]:
    return _unit(context={"languages": ["l"] * count})


def _unit_with_frameworks(count: int) -> dict[str, object]:
    return _unit(context={"frameworks": ["f"] * count})


@pytest.mark.parametrize(
    ("limit_name", "build"),
    [
        ("DOMAINS_MAX_ITEMS", _unit_with_domains),
        ("LANGUAGES_MAX_ITEMS", _unit_with_languages),
        ("FRAMEWORKS_MAX_ITEMS", _unit_with_frameworks),
    ],
)
def test_array_field_enforces_max_items(limit_name: str, build: Callable[[int], dict[str, object]]) -> None:
    schema = cq_schema.load_schema("knowledge_unit")
    limit = getattr(cq_schema, limit_name)

    jsonschema.validate(instance=build(limit), schema=schema)

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=build(limit + 1), schema=schema)
