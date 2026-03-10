"""CRAIC MCP server — shared agent knowledge commons.

Exposes six tools via the Model Context Protocol:
craic_query, craic_propose, craic_confirm, craic_flag, craic_reflect, craic_status.

Searches local store first, then the team API. Degrades gracefully
to local-only mode when the team API is unreachable.
"""

import atexit
import logging
import os
import threading
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .knowledge_unit import (
    Context,
    FlagReason,
    Insight,
    KnowledgeUnit,
    Tier,
    create_knowledge_unit,
)
from .local_store import LocalStore
from .scoring import apply_confirmation, apply_flag, calculate_relevance
from .team_client import TeamClient

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "craic",
    instructions=(
        "CRAIC — Collective Reciprocal Agent Intelligence Commons.\n"
        "Shared knowledge store that helps agents avoid known pitfalls.\n"
        "\n"
        "Environment variables:\n"
        "  CRAIC_LOCAL_DB_PATH  Path to the local SQLite database.\n"
        "                       Default: ~/.craic/local.db.\n"
        "  CRAIC_TEAM_ADDR      URL of the team knowledge API for shared sync.\n"
        "                       Disabled by default. Set to enable team sync,\n"
        "                       e.g. http://localhost:8742."
    ),
)

_MAX_QUERY_LIMIT = 50
_DEFAULT_TEAM_ADDR = ""

_store_local = threading.local()
_store_registry: list[LocalStore] = []
_store_registry_lock = threading.Lock()

_DISABLED_SENTINEL = object()
_team_client: TeamClient | object | None = None
_team_client_lock = threading.Lock()


def _get_store() -> LocalStore:
    """Return the thread-local store, creating it on first access.

    Each thread gets its own LocalStore instance to avoid sharing a single
    SQLite connection across threads. All created stores are tracked in a
    registry so they can be closed at shutdown regardless of which thread
    created them.
    """
    store: LocalStore | None = getattr(_store_local, "store", None)
    if store is None:
        db_path_str = os.environ.get("CRAIC_LOCAL_DB_PATH")
        db_path = Path(db_path_str) if db_path_str else None
        store = LocalStore(db_path=db_path)
        _store_local.store = store
        with _store_registry_lock:
            _store_registry.append(store)
    return store


def _close_store() -> None:
    """Close all registered stores and clear the registry.

    Only safe to call during shutdown (via atexit) or in tests where no
    other threads are accessing stores. Thread-local references on other
    threads become stale after this call.
    """
    with _store_registry_lock:
        for store in _store_registry:
            store.close()
        _store_registry.clear()
    # Clear the thread-local reference for the current thread.
    if getattr(_store_local, "store", None) is not None:
        _store_local.store = None


def _get_team_client() -> TeamClient | None:
    """Return the team API client, creating it on first access.

    Returns None if the team API URL is explicitly disabled (empty string).
    The client is a module-level singleton since httpx.Client is thread-safe.
    Initialisation is guarded by a lock to prevent duplicate creation. A
    sentinel distinguishes "disabled" from "not yet initialised" so the
    disabled path skips the lock on subsequent calls.
    """
    global _team_client  # noqa: PLW0603
    if _team_client is _DISABLED_SENTINEL:
        return None
    if isinstance(_team_client, TeamClient):
        return _team_client
    with _team_client_lock:
        if _team_client is _DISABLED_SENTINEL:
            return None
        if isinstance(_team_client, TeamClient):
            return _team_client
        url = os.environ.get("CRAIC_TEAM_ADDR", _DEFAULT_TEAM_ADDR)
        if not url:
            _team_client = _DISABLED_SENTINEL
            return None
        _team_client = TeamClient(base_url=url)
    return _team_client


def _close_team_client() -> None:
    """Close the team client if open and reset to uninitialised state."""
    global _team_client  # noqa: PLW0603
    with _team_client_lock:
        if isinstance(_team_client, TeamClient):
            _team_client.close()
        _team_client = None


atexit.register(_close_store)
atexit.register(_close_team_client)


def _merge_results(
    local_units: list[KnowledgeUnit],
    team_units: list[KnowledgeUnit] | None,
    query_domains: list[str],
    query_language: str | None,
    query_framework: str | None,
    limit: int,
) -> tuple[list[dict], str]:
    """Merge local and team results, dedup by ID, re-rank, and truncate.

    Args:
        local_units: Results from the local store.
        team_units: Results from the team API, or None if unavailable.
        query_domains: Domain tags used in the query.
        query_language: Language filter used in the query.
        query_framework: Framework filter used in the query.
        limit: Maximum results to return.

    Returns:
        Tuple of (serialised results, source indicator). The source
        reflects whether each store was consulted and returned results,
        not just whether its results survived deduplication.
    """
    if team_units is None:
        return (
            [u.model_dump(mode="json") for u in local_units[:limit]],
            "local",
        )

    seen_ids: set[str] = set()
    merged: list[KnowledgeUnit] = []

    # Local results take precedence for duplicate IDs.
    for unit in local_units:
        if unit.id not in seen_ids:
            seen_ids.add(unit.id)
            merged.append(unit)

    for unit in team_units:
        if unit.id not in seen_ids:
            seen_ids.add(unit.id)
            merged.append(unit)

    # Source reflects which stores were consulted and returned data.
    has_local = len(local_units) > 0
    has_team = len(team_units) > 0

    if has_local and has_team:
        source = "both"
    elif has_team:
        source = "team"
    else:
        source = "local"

    # Re-rank merged results by relevance * confidence.
    scored = []
    for unit in merged:
        relevance = calculate_relevance(
            unit,
            query_domains,
            query_language=query_language,
            query_framework=query_framework,
        )
        scored.append((relevance * unit.evidence.confidence, unit))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = [unit for _, unit in scored[:limit]]

    return [u.model_dump(mode="json") for u in top], source


@mcp.tool()
def craic_query(
    domain: list[str],
    language: str | None = None,
    framework: str | None = None,
    limit: int = 5,
) -> dict:
    """Search for relevant knowledge units by domain tags.

    Searches the local store first, then the team API if available.
    Results are merged, deduplicated by ID, and re-ranked.

    Args:
        domain: Domain tags to search for.
        language: Optional programming language filter.
        framework: Optional framework filter.
        limit: Maximum results to return.

    Returns:
        Dict with ``results`` (list of knowledge unit dicts) and ``source``
        ("local", "team", or "both"), or ``error`` if inputs are invalid.
    """
    cleaned = [d.strip().lower() for d in domain if d.strip()]
    if not cleaned:
        return {"error": "At least one non-empty domain tag is required."}
    if limit < 1:
        return {"error": "limit must be a positive integer."}
    if limit > _MAX_QUERY_LIMIT:
        return {"error": f"limit must not exceed {_MAX_QUERY_LIMIT}."}

    store = _get_store()
    local_results = store.query(
        cleaned,
        language=language,
        framework=framework,
        limit=limit,
    )

    team_results = None
    team_client = _get_team_client()
    if team_client is not None:
        team_results = team_client.query(
            cleaned,
            language=language,
            framework=framework,
            limit=limit,
        )
        if team_results is None:
            logger.info("Team API unavailable for query; using local results only.")

    results, source = _merge_results(
        local_results,
        team_results,
        query_domains=cleaned,
        query_language=language,
        query_framework=framework,
        limit=limit,
    )
    return {"results": results, "source": source}


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
    """Propose a new knowledge unit.

    Always stores in the local store. Also pushes to the team API on a
    best-effort basis for sharing across the team.

    Args:
        summary: Concise description of the insight.
        detail: Fuller explanation.
        action: Recommended action to take.
        domain: Domain tags for categorisation.
        language: Optional single programming language context.
        framework: Optional single framework context.
        pattern: Optional pattern name.

    Returns:
        Dict with ``id``, ``tier``, ``message``, and ``team_id``
        (if pushed to team), or ``error`` if inputs are invalid.
    """
    cleaned_summary = summary.strip()
    cleaned_detail = detail.strip()
    cleaned_action = action.strip()
    if not cleaned_summary or not cleaned_detail or not cleaned_action:
        return {"error": "summary, detail, and action must be non-blank."}
    cleaned_domain = [d.strip().lower() for d in domain if d.strip()]
    if not cleaned_domain:
        return {"error": "At least one non-empty domain tag is required."}
    cleaned_language = language.strip() if language else None
    cleaned_framework = framework.strip() if framework else None
    cleaned_pattern = pattern.strip() if pattern else ""

    store = _get_store()
    context = Context(
        languages=[cleaned_language] if cleaned_language else [],
        frameworks=[cleaned_framework] if cleaned_framework else [],
        pattern=cleaned_pattern,
    )
    unit = create_knowledge_unit(
        domain=cleaned_domain,
        insight=Insight(
            summary=cleaned_summary,
            detail=cleaned_detail,
            action=cleaned_action,
        ),
        context=context,
        tier=Tier.LOCAL,
    )
    store.insert(unit)

    result: dict = {
        "id": unit.id,
        "tier": unit.tier.value,
        "message": f"Knowledge unit {unit.id} stored locally.",
    }

    team_client = _get_team_client()
    if team_client is not None:
        team_unit = team_client.propose(unit)
        if team_unit is not None:
            result["team_id"] = team_unit.id
            result["message"] += f" Also shared to team as {team_unit.id}."
        else:
            logger.info("Team API unavailable for propose; stored locally only.")

    return result


@mcp.tool()
def craic_confirm(unit_id: str) -> dict:
    """Confirm a knowledge unit proved correct, boosting its confidence.

    Checks the local store first, then the team API. If found in both,
    confirms in both stores.

    Args:
        unit_id: Knowledge unit ID to confirm.

    Returns:
        Dict with ``id``, ``new_confidence``, ``confirmations``, and
        ``source``, or ``error`` if the unit was not found in either store.
    """
    store = _get_store()
    local_unit = store.get(unit_id)

    if local_unit is not None:
        confirmed = apply_confirmation(local_unit)
        store.update(confirmed)
        result: dict = {
            "id": confirmed.id,
            "new_confidence": confirmed.evidence.confidence,
            "confirmations": confirmed.evidence.confirmations,
            "source": "local",
        }
        # Best-effort propagation to team.
        team_client = _get_team_client()
        if team_client is not None:
            team_unit = team_client.confirm(unit_id)
            if team_unit is not None:
                result["source"] = "both"
        return result

    # Not in local store — try team API.
    team_client = _get_team_client()
    if team_client is not None:
        team_unit = team_client.confirm(unit_id)
        if team_unit is not None:
            return {
                "id": team_unit.id,
                "new_confidence": team_unit.evidence.confidence,
                "confirmations": team_unit.evidence.confirmations,
                "source": "team",
            }

    return {"error": f"Knowledge unit not found: {unit_id}"}


@mcp.tool()
def craic_flag(unit_id: str, reason: str) -> dict:
    """Flag a knowledge unit as problematic, reducing its confidence.

    Checks the local store first, then the team API. If found in both,
    flags in both stores.

    Args:
        unit_id: Knowledge unit ID to flag.
        reason: One of: stale, incorrect, duplicate.

    Returns:
        Dict with ``id``, ``new_confidence``, ``message``, and ``source``,
        or ``error`` if the unit was not found or the reason is invalid.
    """
    cleaned_reason = reason.strip().lower()
    try:
        flag_reason = FlagReason(cleaned_reason)
    except ValueError:
        valid = ", ".join(r.value for r in FlagReason)
        return {"error": f"Invalid reason: {reason}. Must be one of: {valid}."}

    store = _get_store()
    local_unit = store.get(unit_id)

    if local_unit is not None:
        flagged = apply_flag(local_unit, flag_reason)
        store.update(flagged)
        result: dict = {
            "id": flagged.id,
            "new_confidence": flagged.evidence.confidence,
            "message": f"Knowledge unit {flagged.id} flagged as {cleaned_reason}.",
            "source": "local",
        }
        # Best-effort propagation to team.
        team_client = _get_team_client()
        if team_client is not None:
            team_unit = team_client.flag(unit_id, flag_reason)
            if team_unit is not None:
                result["source"] = "both"
        return result

    # Not in local store — try team API.
    team_client = _get_team_client()
    if team_client is not None:
        team_unit = team_client.flag(unit_id, flag_reason)
        if team_unit is not None:
            return {
                "id": team_unit.id,
                "new_confidence": team_unit.evidence.confidence,
                "message": f"Knowledge unit {team_unit.id} flagged as {cleaned_reason}.",
                "source": "team",
            }

    return {"error": f"Knowledge unit not found: {unit_id}"}


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


@mcp.tool()
def craic_status() -> dict:
    """Return local knowledge store statistics.

    Provides an overview of the local store: total knowledge unit count,
    domain tag breakdown, most recent additions, and confidence score
    distribution across defined buckets.

    Returns:
        Dict with ``total_count``, ``domain_counts``, ``recent``
        (serialised knowledge units), and ``confidence_distribution``.
    """
    store = _get_store()
    result = store.stats()
    return result.model_dump(mode="json")


def main() -> None:
    """Start the CRAIC MCP server."""
    mcp.run()
