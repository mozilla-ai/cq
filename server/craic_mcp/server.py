"""CRAIC MCP server — shared agent knowledge commons.

Exposes five tools via the Model Context Protocol:
craic_query, craic_propose, craic_confirm, craic_flag, craic_reflect.
"""

import atexit
import os
import threading
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .knowledge_unit import (
    Context,
    FlagReason,
    Insight,
    Tier,
    create_knowledge_unit,
)
from .local_store import LocalStore
from .scoring import apply_confirmation, apply_flag

mcp = FastMCP("craic")

_store: LocalStore | None = None
_store_lock = threading.Lock()


def _get_store() -> LocalStore:
    """Return the local store, creating it on first access.

    Thread-safe: uses double-checked locking to ensure a single instance.
    """
    global _store  # noqa: PLW0603
    if _store is None:
        with _store_lock:
            if _store is None:
                db_path_str = os.environ.get("CRAIC_LOCAL_DB_PATH")
                db_path = Path(db_path_str) if db_path_str else None
                _store = LocalStore(db_path=db_path)
    return _store


def _close_store() -> None:
    """Close the store if open."""
    global _store  # noqa: PLW0603
    with _store_lock:
        if _store is not None:
            _store.close()
            _store = None


atexit.register(_close_store)


@mcp.tool()
def craic_query(
    domain: list[str],
    language: str | None = None,
    framework: str | None = None,
    limit: int = 5,
) -> dict:
    """Search for relevant knowledge units by domain tags.

    Args:
        domain: Domain tags to search for.
        language: Optional programming language filter.
        framework: Optional framework filter.
        limit: Maximum results to return.

    Returns:
        Dict with ``results`` (list of knowledge unit dicts) and ``source``,
        or ``error`` if inputs are invalid.
    """
    cleaned = [d.strip() for d in domain if d.strip()]
    if not cleaned:
        return {"error": "At least one non-empty domain tag is required."}
    if limit < 1:
        return {"error": "limit must be a positive integer."}
    store = _get_store()
    results = store.query(cleaned, language=language, framework=framework, limit=limit)
    return {
        "results": [r.model_dump(mode="json") for r in results],
        "source": "local",
    }


@mcp.tool()
def craic_propose(
    summary: str,
    detail: str,
    action: str,
    domain: list[str],
    language: str | None = None,
    framework: str | None = None,
    pattern: str = "",
) -> dict:
    """Propose a new knowledge unit to the local store.

    Accepts a single language and framework value. The underlying data model
    supports lists; use craic_propose multiple times or modify the unit
    directly for multi-value context.

    Args:
        summary: Concise description of the insight.
        detail: Fuller explanation.
        action: Recommended action to take.
        domain: Domain tags for categorisation.
        language: Optional single programming language context.
        framework: Optional single framework context.
        pattern: Optional pattern name.

    Returns:
        Dict with ``id``, ``tier``, and ``message``,
        or ``error`` if required fields are blank or domain is empty.
    """
    if not summary.strip() or not detail.strip() or not action.strip():
        return {"error": "summary, detail, and action must be non-blank."}
    cleaned_domain = [d.strip() for d in domain if d.strip()]
    if not cleaned_domain:
        return {"error": "At least one non-empty domain tag is required."}
    store = _get_store()
    context = Context(
        languages=[language] if language else [],
        frameworks=[framework] if framework else [],
        pattern=pattern,
    )
    unit = create_knowledge_unit(
        domain=cleaned_domain,
        insight=Insight(summary=summary, detail=detail, action=action),
        context=context,
        tier=Tier.LOCAL,
    )
    store.insert(unit)
    return {
        "id": unit.id,
        "tier": unit.tier.value,
        "message": f"Knowledge unit {unit.id} stored locally.",
    }


@mcp.tool()
def craic_confirm(unit_id: str) -> dict:
    """Confirm a knowledge unit proved correct, boosting its confidence.

    Args:
        unit_id: Knowledge unit ID to confirm.

    Returns:
        Dict with ``id``, ``new_confidence``, and ``confirmations``,
        or ``error`` if the unit was not found.
    """
    store = _get_store()
    unit = store.get(unit_id)
    if unit is None:
        return {"error": f"Knowledge unit not found: {unit_id}"}
    confirmed = apply_confirmation(unit)
    store.update(confirmed)
    return {
        "id": confirmed.id,
        "new_confidence": confirmed.evidence.confidence,
        "confirmations": confirmed.evidence.confirmations,
    }


@mcp.tool()
def craic_flag(unit_id: str, reason: str) -> dict:
    """Flag a knowledge unit as problematic, reducing its confidence.

    Args:
        unit_id: Knowledge unit ID to flag.
        reason: One of: stale, incorrect, duplicate.

    Returns:
        Dict with ``id``, ``new_confidence``, and ``message``,
        or ``error`` if the unit was not found or the reason is invalid.
    """
    store = _get_store()
    unit = store.get(unit_id)
    if unit is None:
        return {"error": f"Knowledge unit not found: {unit_id}"}
    try:
        flag_reason = FlagReason(reason)
    except ValueError:
        valid = ", ".join(r.value for r in FlagReason)
        return {"error": f"Invalid reason: {reason}. Must be one of: {valid}."}
    flagged = apply_flag(unit, flag_reason)
    store.update(flagged)
    return {
        "id": flagged.id,
        "new_confidence": flagged.evidence.confidence,
        "message": f"Knowledge unit {flagged.id} flagged as {reason}.",
    }


@mcp.tool()
def craic_reflect(session_context: str) -> dict:
    """Analyse session context for candidate knowledge units worth sharing.

    The agent passes its session conversation context. Returns candidates
    that may be worth proposing as knowledge units. Submit approved
    candidates individually via craic_propose.

    This tool is a stub in the PoC. Session mining intelligence lives in
    the /craic:reflect slash command (issue #9).

    Args:
        session_context: The session conversation context to analyse.

    Returns:
        Dict with ``candidates`` list, ``message``, and ``status``.
    """
    if not session_context.strip():
        return {
            "candidates": [],
            "message": "Empty session context provided.",
            "status": "stub",
        }
    return {
        "candidates": [],
        "message": "Session context received. Identify candidate knowledge units and submit each via craic_propose.",
        "status": "stub",
    }


def main() -> None:
    """Start the CRAIC MCP server."""
    mcp.run()
