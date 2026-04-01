"""Confidence scoring and relevance functions for knowledge units."""

from datetime import UTC, datetime

from .knowledge_unit import Flag, FlagReason, KnowledgeUnit

CONFIRMATION_BOOST = 0.1
FLAG_PENALTY = 0.15
CONFIDENCE_CEILING = 1.0
CONFIDENCE_FLOOR = 0.0


def apply_confirmation(unit: KnowledgeUnit) -> KnowledgeUnit:
    """Increment confirmations and boost confidence, capped at 1.0."""
    new_confidence = min(unit.evidence.confidence + CONFIRMATION_BOOST, CONFIDENCE_CEILING)
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


def apply_flag(unit: KnowledgeUnit, reason: FlagReason) -> KnowledgeUnit:
    """Reduce confidence and record the flag reason."""
    new_confidence = max(unit.evidence.confidence - FLAG_PENALTY, CONFIDENCE_FLOOR)
    new_flag = Flag(reason=reason)
    return unit.model_copy(
        update={
            "evidence": unit.evidence.model_copy(update={"confidence": new_confidence}),
            "flags": [*unit.flags, new_flag],
        }
    )


def calculate_relevance(
    unit: KnowledgeUnit,
    query_domains: list[str],
    query_language: str | None = None,
    query_framework: str | None = None,
) -> float:
    """Score relevance from 0.0 to 1.0 based on domain overlap and context match.

    Domain overlap is the primary signal (weighted at 0.7).
    Language and framework matches are secondary signals (0.15 each).
    """
    domain_weight = 0.7
    language_weight = 0.15
    framework_weight = 0.15

    # Domain overlap scored by Jaccard similarity.
    unit_domains = set(unit.domain)
    query_domain_set = set(query_domains)
    if unit_domains or query_domain_set:
        domain_score = len(unit_domains & query_domain_set) / len(unit_domains | query_domain_set)
    else:
        domain_score = 0.0

    # Language match is binary.
    language_score = 0.0
    if query_language and query_language in unit.context.languages:
        language_score = 1.0

    # Framework match is binary.
    framework_score = 0.0
    if query_framework and query_framework in unit.context.frameworks:
        framework_score = 1.0

    return domain_weight * domain_score + language_weight * language_score + framework_weight * framework_score
