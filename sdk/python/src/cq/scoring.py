"""Confidence scoring and relevance functions for knowledge units."""

from datetime import UTC, datetime

from cq_schema import (
    CONFIDENCE_CEILING as _CONFIDENCE_CEILING,
)
from cq_schema import (
    CONFIDENCE_FLOOR as _CONFIDENCE_FLOOR,
)
from cq_schema import (
    CONFIRMATION_BOOST,
    FLAG_PENALTY,
)
from cq_schema import (
    DOMAIN_WEIGHT as _DOMAIN_WEIGHT,
)
from cq_schema import (
    FRAMEWORK_WEIGHT as _FRAMEWORK_WEIGHT,
)
from cq_schema import (
    LANGUAGE_WEIGHT as _LANGUAGE_WEIGHT,
)
from cq_schema import (
    PATTERN_WEIGHT as _PATTERN_WEIGHT,
)

from ._util import _as_list
from .models import Flag, FlagReason, KnowledgeUnit

_RELEVANCE_CEILING = 1.0
_RELEVANCE_FLOOR = 0.0


def apply_confirmation(unit: KnowledgeUnit) -> KnowledgeUnit:
    """Increment confirmations and boost confidence, capped at 1.0."""
    new_confidence = min(unit.evidence.confidence + CONFIRMATION_BOOST, _CONFIDENCE_CEILING)
    new_confirmations = unit.evidence.confirmations + 1
    return unit.model_copy(
        update={
            "evidence": unit.evidence.model_copy(
                update={
                    "confidence": new_confidence,
                    "confirmations": new_confirmations,
                    "last_confirmed": datetime.now(UTC),
                }
            )
        }
    )


def apply_flag(
    unit: KnowledgeUnit,
    reason: FlagReason,
    *,
    duplicate_of: str | None = None,
) -> KnowledgeUnit:
    """Reduce confidence and record the flag reason."""
    new_confidence = max(unit.evidence.confidence - FLAG_PENALTY, _CONFIDENCE_FLOOR)
    new_flag = Flag(reason=reason, duplicate_of=duplicate_of)
    return unit.model_copy(
        update={
            "evidence": unit.evidence.model_copy(update={"confidence": new_confidence}),
            "flags": [*unit.flags, new_flag],
        }
    )


def calculate_relevance(
    unit: KnowledgeUnit,
    query_domains: list[str],
    query_languages: list[str] | None = None,
    query_frameworks: list[str] | None = None,
    query_pattern: str = "",
) -> float:
    """Score relevance from 0.0 to 1.0 based on domain overlap and context match.

    Domain overlap is the primary signal. Language, framework, and pattern
    matches are secondary signals. Concrete weights live in cq_schema's
    canonical scoring.values.json.
    """
    query_domains = _as_list(query_domains)
    if query_languages is not None:
        query_languages = _as_list(query_languages)
    if query_frameworks is not None:
        query_frameworks = _as_list(query_frameworks)

    # Domain overlap scored by Jaccard similarity.
    unit_domains = set(unit.domains)
    query_domain_set = set(query_domains)
    if unit_domains or query_domain_set:
        domain_score = len(unit_domains & query_domain_set) / len(unit_domains | query_domain_set)
    else:
        domain_score = 0.0

    # Language match: any overlap between query and unit languages.
    language_score = 0.0
    if query_languages and any(lang in unit.context.languages for lang in query_languages):
        language_score = 1.0

    # Framework match: any overlap between query and unit frameworks.
    framework_score = 0.0
    if query_frameworks and any(fw in unit.context.frameworks for fw in query_frameworks):
        framework_score = 1.0

    # Pattern match: exact case-insensitive equality between query and unit pattern.
    pattern_score = (
        1.0 if query_pattern and unit.context.pattern and query_pattern.lower() == unit.context.pattern.lower() else 0.0
    )

    score = (
        _DOMAIN_WEIGHT * domain_score
        + _LANGUAGE_WEIGHT * language_score
        + _FRAMEWORK_WEIGHT * framework_score
        + _PATTERN_WEIGHT * pattern_score
    )
    return min(max(score, _RELEVANCE_FLOOR), _RELEVANCE_CEILING)
