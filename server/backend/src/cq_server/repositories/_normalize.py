"""Tag normalization shared between concrete stores."""

from cq.models import KnowledgeUnit


def normalize_domains(domains: list[str]) -> list[str]:
    """Lowercase, strip whitespace, drop empties, and deduplicate domain tags."""
    return list(dict.fromkeys(d.strip().lower() for d in domains if d.strip()))


def normalize_unit_tags(unit: KnowledgeUnit) -> KnowledgeUnit:
    """Return a copy of unit with its domain, language, and framework tags normalized.

    NOTE: callers must reject a unit whose returned domains list is empty.
    A unit whose domains all normalize away has no usable domain.
    """
    return unit.model_copy(
        update={
            "domains": normalize_domains(unit.domains),
            "context": unit.context.model_copy(
                update={
                    "languages": normalize_domains(unit.context.languages),
                    "frameworks": normalize_domains(unit.context.frameworks),
                }
            ),
        }
    )
