"""Tests that validate Python SDK serialised models against the canonical JSON Schemas.

These tests are the "schema-as-oracle" pattern: they ensure the hand-written
Pydantic models stay aligned with the canonical schema documents shipped in
the cq-schema package. If a model field is renamed or its serialisation
changes shape, the canonical schema validation will fail here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import cq_schema
import jsonschema
import pytest
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

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
from cq.store import StoreStats


def _make_full_unit() -> KnowledgeUnit:
    now = datetime.now(UTC)
    base = create_knowledge_unit(
        domains=["databases"],
        insight=Insight(summary="s", detail="d", action="a"),
        context=Context(languages=["python"], frameworks=["sqlmodel"], pattern="orm"),
        tier=Tier.LOCAL,
        created_by="test-agent",
    )
    return base.model_copy(
        update={
            "evidence": Evidence(
                confidence=0.7,
                confirmations=2,
                first_observed=now,
                last_confirmed=now,
            ),
            "flags": [Flag(reason=FlagReason.STALE, timestamp=now)],
        }
    )


def test_full_knowledge_unit_validates_against_canonical_schema() -> None:
    # The store serialises with exclude_none=True so persisted JSON matches
    # the canonical schema, which models optional fields as omitted (not
    # nullable). Round-trip the unit through that path so the test reflects
    # what downstream consumers will see.
    unit = _make_full_unit()
    schema = cq_schema.load_schema("knowledge_unit")
    payload = json.loads(unit.model_dump_json(exclude_none=True))
    jsonschema.validate(instance=payload, schema=schema)


def test_knowledge_unit_with_extensions_validates_against_canonical_schema() -> None:
    unit = create_knowledge_unit(
        domains=["api"],
        insight=Insight(summary="s", detail="d", action="a"),
    )
    unit = unit.model_copy(update={"extensions": {"impl:severity": "high", "impl:tags": ["a", "b"]}})
    schema = cq_schema.load_schema("knowledge_unit")
    payload = json.loads(unit.model_dump_json(exclude_none=True))
    jsonschema.validate(instance=payload, schema=schema)
    assert payload["extensions"] == {"impl:severity": "high", "impl:tags": ["a", "b"]}


def test_minimal_knowledge_unit_validates_against_canonical_schema() -> None:
    unit = create_knowledge_unit(
        domains=["databases"],
        insight=Insight(summary="s", detail="d", action="a"),
    )
    schema = cq_schema.load_schema("knowledge_unit")
    payload = json.loads(unit.model_dump_json(exclude_none=True))
    jsonschema.validate(instance=payload, schema=schema)


@pytest.mark.parametrize("reason", [FlagReason.STALE, FlagReason.INCORRECT, FlagReason.DUPLICATE])
def test_flag_reasons_match_canonical_enum(reason: FlagReason) -> None:
    schema = cq_schema.load_schema("knowledge_unit")
    flag_def = schema["$defs"]["FlagReason"]
    assert reason.value in flag_def["enum"]


@pytest.mark.parametrize("tier", [Tier.LOCAL, Tier.PRIVATE, Tier.PUBLIC])
def test_tiers_match_canonical_enum(tier: Tier) -> None:
    schema = cq_schema.load_schema("knowledge_unit")
    tier_def = schema["$defs"]["Tier"]
    assert tier.value in tier_def["enum"]


def _stats_validator() -> jsonschema.Draft202012Validator:
    """Build a validator for stats.json with the knowledge_unit $ref resolvable."""
    stats_schema = cq_schema.load_schema("stats")
    ku_schema = cq_schema.load_schema("knowledge_unit")
    registry = Registry().with_resources(
        [
            (
                "https://mozilla-ai.github.io/cq/schema/knowledge_unit.json",
                Resource.from_contents(ku_schema, default_specification=DRAFT202012),
            ),
        ]
    )
    return jsonschema.Draft202012Validator(stats_schema, registry=registry)


def test_full_store_stats_validates_against_canonical_schema() -> None:
    unit = _make_full_unit()
    stats = StoreStats(
        total_count=42,
        domain_counts={"api": 20, "ci": 12, "testing": 10},
        recent=[unit],
        confidence_distribution={"0.0-0.3": 5, "0.3-0.5": 10, "0.5-0.7": 15, "0.7-1.0": 12},
        tier_counts={Tier.LOCAL: 30, Tier.PRIVATE: 10, Tier.PUBLIC: 2},
        warnings=["remote stats unavailable"],
    )
    payload = json.loads(stats.model_dump_json(exclude_none=True))
    _stats_validator().validate(payload)


def test_minimal_store_stats_validates_against_canonical_schema() -> None:
    stats = StoreStats(
        total_count=0,
        domain_counts={},
        confidence_distribution={},
        tier_counts={},
    )
    payload = json.loads(stats.model_dump_json(exclude_none=True))
    _stats_validator().validate(payload)


def test_knowledge_unit_field_coverage() -> None:
    """Every KnowledgeUnit field must appear in the canonical schema and vice versa."""
    schema = cq_schema.load_schema("knowledge_unit")
    schema_props = set(schema["properties"])
    model_fields = set(KnowledgeUnit.model_fields)
    missing = model_fields - schema_props
    assert not missing, f"KnowledgeUnit fields missing from knowledge_unit.json: {missing}"
    extra = schema_props - model_fields
    assert not extra, f"knowledge_unit.json properties not present in KnowledgeUnit: {extra}"


def test_store_stats_field_coverage() -> None:
    """Every StoreStats field must appear in the canonical stats schema."""
    schema = cq_schema.load_schema("stats")
    schema_props = set(schema["properties"])
    model_fields = set(StoreStats.model_fields)
    missing = model_fields - schema_props
    assert not missing, f"StoreStats fields missing from stats.json: {missing}"
    extra = schema_props - model_fields
    assert not extra, f"stats.json properties not present in StoreStats: {extra}"
