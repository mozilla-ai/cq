"""Canonical JSON Schemas and parsed scoring values for cq.

This package ships the JSON Schema documents that define cq's wire format
together with a small set of scoring constants parsed from
`scoring.values.json`. Consumers receive raw schema documents (as bytes
or parsed dicts) plus the constants; they bring their own JSON Schema
validator. Adding one as a hard dependency would force every consumer to
install it, even those that only need the constants.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

__all__ = [
    "CONFIDENCE_CEILING",
    "CONFIDENCE_FLOOR",
    "CONFIRMATION_BOOST",
    "DOMAIN_WEIGHT",
    "FLAG_PENALTY",
    "FRAMEWORK_WEIGHT",
    "INITIAL_CONFIDENCE",
    "LANGUAGE_WEIGHT",
    "PATTERN_WEIGHT",
    "load_schema",
    "load_schema_bytes",
]

_DATA = files("cq_schema") / "_data"


def load_schema_bytes(name: str) -> bytes:
    """Return the raw bytes of a bundled JSON Schema document.

    Args:
        name: Schema filename without extension (e.g. "knowledge_unit").

    Returns:
        Raw schema file contents.

    Raises:
        FileNotFoundError: If the named schema is not bundled.
    """
    return (_DATA / f"{name}.json").read_bytes()


def load_schema(name: str) -> dict[str, Any]:
    """Return a bundled JSON Schema document parsed as a dict.

    Args:
        name: Schema filename without extension (e.g. "knowledge_unit").

    Returns:
        Parsed schema document.

    Raises:
        FileNotFoundError: If the named schema is not bundled.
        json.JSONDecodeError: If the bundled file is not valid JSON.
    """
    return json.loads(load_schema_bytes(name))


_values = json.loads((_DATA / "scoring.values.json").read_text(encoding="utf-8"))
_relevance = _values["relevance_weights"]
_confidence = _values["confidence_constants"]

DOMAIN_WEIGHT: float = _relevance["domain_weight"]
LANGUAGE_WEIGHT: float = _relevance["language_weight"]
FRAMEWORK_WEIGHT: float = _relevance["framework_weight"]
PATTERN_WEIGHT: float = _relevance["pattern_weight"]

INITIAL_CONFIDENCE: float = _confidence["initial_confidence"]
CONFIRMATION_BOOST: float = _confidence["confirmation_boost"]
FLAG_PENALTY: float = _confidence["flag_penalty"]
CONFIDENCE_CEILING: float = _confidence["ceiling"]
CONFIDENCE_FLOOR: float = _confidence["floor"]
