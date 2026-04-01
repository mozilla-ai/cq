"""Confidence scoring and relevance functions for knowledge units."""

from datetime import UTC, datetime

from ._util import _as_list
from .models import Flag, FlagReason, KnowledgeUnit

CONFIRMATION_BOOST = 0.1
FLAG_PENALTY = 0.15
_CONFIDENCE_CEILING = 1.0
_CONFIDENCE_FLOOR = 0.0


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
) -> float:
    """Score relevance from 0.0 to 1.0 based on domain overlap and context match.

    Domain overlap is the primary signal (weighted at 0.7).
    Language and framework matches are secondary signals (0.15 each).
    """
    query_domains = _as_list(query_domains)
    if query_languages is not None:
        query_languages = _as_list(query_languages)
    if query_frameworks is not None:
        query_frameworks = _as_list(query_frameworks)

    domain_weight = 0.7
    language_weight = 0.15
    framework_weight = 0.15

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

    return domain_weight * domain_score + language_weight * language_score + framework_weight * framework_score
