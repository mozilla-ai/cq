"""Tests that validate backend-serialised units against the canonical schema."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import cq_schema
import jsonschema
from cq.models import Context, Evidence, Flag, FlagReason, Insight, KnowledgeUnit, Tier, create_knowledge_unit


def _make_full_unit() -> KnowledgeUnit:
    now = datetime.now(UTC)
    base = create_knowledge_unit(
        domains=["databases"],
        insight=Insight(summary="s", detail="d", action="a"),
        context=Context(languages=["python"], frameworks=["sqlalchemy"], pattern="orm"),
        tier=Tier.PRIVATE,
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
