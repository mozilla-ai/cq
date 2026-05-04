"""Tests that validate server-serialised KnowledgeUnits against the canonical JSON Schema.

These are the "schema-as-oracle" pattern: they ensure what the server
stores in SQLite (via ``unit.model_dump_json()``) round-trips through
the canonical schema document shipped in ``cq-schema``. If the SDK
model's serialisation drifts from the schema, these fail loudly.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import cq_schema
import jsonschema
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
    # SqliteStore persists units via ``unit.model_dump_json()``; the
    # canonical schema models optional fields as omitted (not nullable),
    # so round-trip the unit through ``exclude_none=True`` to match what
    # downstream consumers actually see.
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
