"""Tests for the cq_schema package."""

from __future__ import annotations

import json
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


def test_scoring_values_validates_against_scoring_schema() -> None:
    schema = cq_schema.load_schema("scoring")
    values = json.loads(cq_schema.load_schema_bytes("scoring.values"))
    jsonschema.validate(instance=values, schema=schema)


def test_knowledge_unit_fixtures_validate() -> None:
    schema = cq_schema.load_schema("knowledge_unit")
    fixtures_dir = Path(__file__).resolve().parent.parent.parent / "fixtures"
    for fixture_name in ("valid-unit.json", "minimal-unit.json", "flagged-unit.json", "duplicate-flag.json"):
        instance = json.loads((fixtures_dir / fixture_name).read_text(encoding="utf-8"))
        jsonschema.validate(instance=instance, schema=schema)
