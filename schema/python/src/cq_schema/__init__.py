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
_SCORING_CONSTANT_NAMES = {
    "DOMAIN_WEIGHT",
    "LANGUAGE_WEIGHT",
    "FRAMEWORK_WEIGHT",
    "PATTERN_WEIGHT",
    "INITIAL_CONFIDENCE",
    "CONFIRMATION_BOOST",
    "FLAG_PENALTY",
    "CONFIDENCE_CEILING",
    "CONFIDENCE_FLOOR",
}
_scoring_constants: dict[str, float] | None = None


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


def _load_scoring_constants() -> dict[str, float]:
    try:
        raw = (_DATA / "scoring.values.json").read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise RuntimeError(
            "cq_schema data files are missing; run `make sync-schema` (or `make setup-schema`) from the repository root"
        ) from error

    values = json.loads(raw)
    relevance = values["relevance_weights"]
    confidence = values["confidence_constants"]
    return {
        "DOMAIN_WEIGHT": float(relevance["domain_weight"]),
        "LANGUAGE_WEIGHT": float(relevance["language_weight"]),
        "FRAMEWORK_WEIGHT": float(relevance["framework_weight"]),
        "PATTERN_WEIGHT": float(relevance["pattern_weight"]),
        "INITIAL_CONFIDENCE": float(confidence["initial_confidence"]),
        "CONFIRMATION_BOOST": float(confidence["confirmation_boost"]),
        "FLAG_PENALTY": float(confidence["flag_penalty"]),
        "CONFIDENCE_CEILING": float(confidence["ceiling"]),
        "CONFIDENCE_FLOOR": float(confidence["floor"]),
    }


def __getattr__(name: str) -> float:
    if name not in _SCORING_CONSTANT_NAMES:
        raise AttributeError(f"module 'cq_schema' has no attribute {name!r}")

    global _scoring_constants
    if _scoring_constants is None:
        _scoring_constants = _load_scoring_constants()
    return _scoring_constants[name]
