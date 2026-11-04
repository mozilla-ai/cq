"""Tag normalization shared between concrete stores."""

from cq.models import KnowledgeUnit


def normalize_domains(domains: list[str]) -> list[str]:
    """Lowercase, strip whitespace, drop empties, and deduplicate domain tags."""
    return list(dict.fromkeys(d.strip().lower() for d in domains if d.strip()))


def normalize_unit_tags(unit: KnowledgeUnit) -> KnowledgeUnit:
    """Return a validated copy of unit with its domain, language, and framework tags normalized.

    Raises:
        ValueError: If no domain survives normalization, or a normalized tag no
            longer satisfies the schema.
    """
    data = unit.model_dump()
    data["domains"] = normalize_domains(unit.domains)
    data["context"]["languages"] = normalize_domains(unit.context.languages)
    data["context"]["frameworks"] = normalize_domains(unit.context.frameworks)
    if not data["domains"]:
        raise ValueError("At least one non-empty domain is required")

    return KnowledgeUnit.model_validate(data)
