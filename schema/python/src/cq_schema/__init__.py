"""Canonical JSON Schemas and parsed constants for cq.

This package ships the JSON Schema documents that define cq's wire format
together with a small set of constants parsed from those documents: the
scoring values from `scoring.values.json` and the free-text length and
cardinality ceilings declared on `knowledge_unit.json`. Consumers receive
raw schema documents (as bytes or parsed dicts) plus the constants; they
bring their own JSON Schema validator. Adding one as a hard dependency
would force every consumer to install it, even those that only need the
constants.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import TYPE_CHECKING, Any

__all__ = [
    "ACTION_MAX_LENGTH",
    "CONFIDENCE_CEILING",
    "CONFIDENCE_FLOOR",
    "CONFIRMATION_BOOST",
    "CREATED_BY_MAX_LENGTH",
    "DETAIL_MAX_LENGTH",
    "DOMAIN_MAX_LENGTH",
    "DOMAIN_WEIGHT",
    "DOMAINS_MAX_ITEMS",
    "FLAG_DETAIL_MAX_LENGTH",
    "FLAG_PENALTY",
    "FRAMEWORK_MAX_LENGTH",
    "FRAMEWORK_WEIGHT",
    "FRAMEWORKS_MAX_ITEMS",
    "INITIAL_CONFIDENCE",
    "LANGUAGE_MAX_LENGTH",
    "LANGUAGE_WEIGHT",
    "LANGUAGES_MAX_ITEMS",
    "PATTERN_MAX_LENGTH",
    "PATTERN_WEIGHT",
    "SUMMARY_MAX_LENGTH",
    "load_schema",
    "load_schema_bytes",
]

if TYPE_CHECKING:
    # __getattr__ serves these at runtime and must return a single type for
    # both groups, so it widens to int | float. Declare each constant's
    # concrete type here so static checkers see the ceilings as int and the
    # scoring values as float.
    ACTION_MAX_LENGTH: int
    CONFIDENCE_CEILING: float
    CONFIDENCE_FLOOR: float
    CONFIRMATION_BOOST: float
    CREATED_BY_MAX_LENGTH: int
    DETAIL_MAX_LENGTH: int
    DOMAIN_MAX_LENGTH: int
    DOMAIN_WEIGHT: float
    DOMAINS_MAX_ITEMS: int
    FLAG_DETAIL_MAX_LENGTH: int
    FLAG_PENALTY: float
    FRAMEWORK_MAX_LENGTH: int
    FRAMEWORK_WEIGHT: float
    FRAMEWORKS_MAX_ITEMS: int
    INITIAL_CONFIDENCE: float
    LANGUAGE_MAX_LENGTH: int
    LANGUAGE_WEIGHT: float
    LANGUAGES_MAX_ITEMS: int
    PATTERN_MAX_LENGTH: int
    PATTERN_WEIGHT: float
    SUMMARY_MAX_LENGTH: int

_DATA = files("cq_schema") / "_data"

# JSON keys used to navigate knowledge_unit.json.
_KEY_CONTEXT = "Context"
_KEY_DEFS = "$defs"
_KEY_FLAG = "Flag"
_KEY_INSIGHT = "Insight"
_KEY_ITEMS = "items"
_KEY_MAX_ITEMS = "maxItems"
_KEY_MAX_LENGTH = "maxLength"
_KEY_PROPERTIES = "properties"

_scoring_constants: dict[str, float] | None = None
_schema_limits: dict[str, int] | None = None


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
    """Parse the relevance weights and confidence constants from scoring.values.json.

    Returns:
        Mapping of each public scoring constant name to its float value.

    Raises:
        RuntimeError: If the bundled schema data files are missing.
    """
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


def _load_schema_limits() -> dict[str, int]:
    """Parse the free-text length and array-cardinality ceilings from knowledge_unit.json.

    Returns:
        Mapping of each public limit constant name to its integer value.

    Raises:
        RuntimeError: If the bundled schema data files are missing.
    """
    try:
        raw = (_DATA / "knowledge_unit.json").read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise RuntimeError(
            "cq_schema data files are missing; run `make sync-schema` (or `make setup-schema`) from the repository root"
        ) from error

    schema = json.loads(raw)
    properties = schema[_KEY_PROPERTIES]
    defs = schema[_KEY_DEFS]
    insight = defs[_KEY_INSIGHT][_KEY_PROPERTIES]
    context = defs[_KEY_CONTEXT][_KEY_PROPERTIES]
    flag = defs[_KEY_FLAG][_KEY_PROPERTIES]
    return {
        "ACTION_MAX_LENGTH": int(insight["action"][_KEY_MAX_LENGTH]),
        "CREATED_BY_MAX_LENGTH": int(properties["created_by"][_KEY_MAX_LENGTH]),
        "DETAIL_MAX_LENGTH": int(insight["detail"][_KEY_MAX_LENGTH]),
        "DOMAIN_MAX_LENGTH": int(properties["domains"][_KEY_ITEMS][_KEY_MAX_LENGTH]),
        "DOMAINS_MAX_ITEMS": int(properties["domains"][_KEY_MAX_ITEMS]),
        "FLAG_DETAIL_MAX_LENGTH": int(flag["detail"][_KEY_MAX_LENGTH]),
        "FRAMEWORK_MAX_LENGTH": int(context["frameworks"][_KEY_ITEMS][_KEY_MAX_LENGTH]),
        "FRAMEWORKS_MAX_ITEMS": int(context["frameworks"][_KEY_MAX_ITEMS]),
        "LANGUAGE_MAX_LENGTH": int(context["languages"][_KEY_ITEMS][_KEY_MAX_LENGTH]),
        "LANGUAGES_MAX_ITEMS": int(context["languages"][_KEY_MAX_ITEMS]),
        "PATTERN_MAX_LENGTH": int(context["pattern"][_KEY_MAX_LENGTH]),
        "SUMMARY_MAX_LENGTH": int(insight["summary"][_KEY_MAX_LENGTH]),
    }


def __getattr__(name: str) -> int | float:
    if name not in __all__:
        raise AttributeError(f"module 'cq_schema' has no attribute {name!r}")

    global _scoring_constants, _schema_limits
    if _scoring_constants is None:
        _scoring_constants = _load_scoring_constants()
    if name in _scoring_constants:
        return _scoring_constants[name]

    if _schema_limits is None:
        _schema_limits = _load_schema_limits()
    if name in _schema_limits:
        return _schema_limits[name]

    raise AttributeError(f"module 'cq_schema' has no attribute {name!r}")
