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
