"""cq MCP server — shared agent knowledge commons.

Exposes six tools via the Model Context Protocol:
query, propose, confirm, flag, reflect, status.

Searches local store first, then the team API. Degrades gracefully
to local-only mode when the team API is unreachable.
"""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
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
from .local_store import LocalStore, TeamSyncStatus
from .scoring import apply_confirmation, apply_flag, calculate_relevance
from .team_client import TeamClient, TeamRejectedError

logger = logging.getLogger(__name__)

_MAX_QUERY_LIMIT = 50
_DRAIN_BATCH_SIZE = 50
_DRAIN_CONCURRENCY = 5
_DEFAULT_TEAM_ADDR = ""

# Module-level singleton. Initialisation happens on the event loop thread
# (single-threaded, so no lock needed). Store methods are called via
# asyncio.to_thread(), which runs them on executor threads. LocalStore
# serialises all connection access with an internal threading.Lock.
_store: LocalStore | None = None


def _get_store() -> LocalStore:
    """Return the module-level store, creating it on first access.

    Called from the event loop thread only — no locking required.
    Store methods are later dispatched to executor threads via
    asyncio.to_thread().
    """
    global _store  # noqa: PLW0603
    if _store is None:
        db_path_str = os.environ.get("CQ_LOCAL_DB_PATH")
        db_path = Path(db_path_str) if db_path_str else None
        _store = LocalStore(db_path=db_path)
    return _store


def _close_store() -> None:
    """Close the store and reset to uninitialised state."""
    global _store  # noqa: PLW0603
    if _store is not None:
        _store.close()
        _store = None


_DISABLED_SENTINEL = object()
# Initialised on the event loop thread (single-threaded, no lock needed).
_team_client: TeamClient | object | None = None


def _get_team_client() -> TeamClient | None:
    """Return the team API client, creating it on first access.

    Returns None when CQ_TEAM_ADDR is empty or unset (local-only mode).
    Called from the event loop thread only — no locking required.
    """
    global _team_client  # noqa: PLW0603
    if _team_client is _DISABLED_SENTINEL:
        return None
    if isinstance(_team_client, TeamClient):
        return _team_client
    url = os.environ.get("CQ_TEAM_ADDR", _DEFAULT_TEAM_ADDR)
    if not url:
        _team_client = _DISABLED_SENTINEL
        return None
    _team_client = TeamClient(base_url=url)
    return _team_client


async def _close_team_client() -> None:
    """Close the team client if open and reset to uninitialised state."""
    global _team_client  # noqa: PLW0603
    if isinstance(_team_client, TeamClient):
        await _team_client.close()
    _team_client = None


# Tracks how many KUs were promoted at startup for status reporting.
# None means no drain has run (CQ_TEAM_ADDR not configured).
_drain_promoted_count: int | None = None


async def _drain_local_to_team() -> None:
    """Retry team sync for locally-stored KUs still marked pending.

    Runs once at MCP server startup when CQ_TEAM_ADDR is configured.
    Only KUs explicitly marked as pending sync are retried.
    Successfully synced KUs remain in the local store and have their
    sync metadata updated in place. Rejections are marked rejected so
    they are not retried indefinitely. Transport failures remain pending
    for the next startup repair pass.
    """
    global _drain_promoted_count  # noqa: PLW0603
    team_client = _get_team_client()
    if team_client is None:
        return

    store = _get_store()
    units = await asyncio.to_thread(store.pending_sync_units)
    if not units:
        _drain_promoted_count = 0
        return

    sem = asyncio.Semaphore(_DRAIN_CONCURRENCY)

    async def _promote(unit: KnowledgeUnit) -> bool:
        async with sem:
            attempted_at = datetime.now(UTC)
            try:
                result = await team_client.propose(unit)
            except TeamRejectedError as exc:
                await asyncio.to_thread(
                    store.update_team_sync_status,
                    unit.id,
                    TeamSyncStatus.REJECTED,
                    error=exc.detail,
                    attempted_at=attempted_at,
                )
                logger.warning(
                    "Team API rejected local KU %s; marked rejected locally.",
                    unit.id,
                )
                return False
            if result is None:
                await asyncio.to_thread(
                    store.update_team_sync_status,
                    unit.id,
                    TeamSyncStatus.PENDING,
                    error="Team API unreachable during startup sync.",
                    attempted_at=attempted_at,
                )
                logger.warning(
                    "Team API unreachable for local KU %s; will retry next startup.",
                    unit.id,
                )
                return False
            await asyncio.to_thread(
                store.update_team_sync_status,
                unit.id,
                TeamSyncStatus.SYNCED,
                error=None,
                attempted_at=attempted_at,
            )
            return True

    # Process in fixed-size batches to bound the number of in-flight tasks.
    promoted = 0
    for i in range(0, len(units), _DRAIN_BATCH_SIZE):
        batch = units[i : i + _DRAIN_BATCH_SIZE]
        results = await asyncio.gather(*[_promote(u) for u in batch], return_exceptions=True)
        for unit, result in zip(batch, results, strict=True):
            if isinstance(result, BaseException):
                logger.error(
                    "Unexpected error promoting KU %s: %s",
                    unit.id,
                    result,
                )
            elif result is True:
                promoted += 1

    _drain_promoted_count = promoted
    logger.info("Synced %d/%d pending local KUs to team.", promoted, len(units))


@asynccontextmanager
async def _lifespan(_server: FastMCP) -> AsyncIterator[None]:
    """Manage MCP server startup and shutdown.

    On startup: retries pending local-to-team sync work (if configured).
    On shutdown: closes the team client and local store.
    """
    await _drain_local_to_team()
    try:
        yield
    finally:
        await _close_team_client()
        _close_store()


mcp = FastMCP(
    "cq",
    instructions=(
        "cq — shared agent knowledge commons.\n"
        "Shared knowledge store that helps agents avoid known pitfalls.\n"
        "\n"
        "Environment variables:\n"
        "  CQ_LOCAL_DB_PATH  Path to the local SQLite database.\n"
        "                    Default: $XDG_DATA_HOME/cq/local.db\n"
        "                    (~/.local/share/cq/local.db).\n"
        "  CQ_TEAM_ADDR      URL of the team knowledge API for shared sync.\n"
        "                    Disabled by default. Set to enable team sync,\n"
        "                    e.g. http://localhost:8742."
    ),
    lifespan=_lifespan,
)


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
        Tuple of (serialised results, source indicator). Source reflects
        whether each store was consulted and returned results, not just
        whether its results survived deduplication.
    """
    if team_units is None:
        return (
            [u.model_dump(mode="json") for u in local_units[:limit]],
            "local",
        )

    local_by_id = {unit.id: unit for unit in local_units}
    team_by_id = {unit.id: unit for unit in team_units}
    merged: list[KnowledgeUnit] = []

    for unit_id in dict.fromkeys([*local_by_id.keys(), *team_by_id.keys()]):
        local_unit = local_by_id.get(unit_id)
        team_unit = team_by_id.get(unit_id)
        if local_unit is None:
            merged.append(team_unit)
            continue
        if team_unit is None:
            merged.append(local_unit)
            continue
        merged.append(_prefer_merged_unit(local_unit, team_unit))

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


def _prefer_merged_unit(local_unit: KnowledgeUnit, team_unit: KnowledgeUnit) -> KnowledgeUnit:
    """Choose the best representation for a KU present in both stores."""
    local_last = local_unit.evidence.last_confirmed or local_unit.evidence.first_observed
    team_last = team_unit.evidence.last_confirmed or team_unit.evidence.first_observed
    if local_last and team_last:
        if team_last > local_last:
            return team_unit
        if local_last > team_last:
            return local_unit
    elif team_last is not None:
        return team_unit
    elif local_last is not None:
        return local_unit
    return team_unit


@mcp.tool(name="query")
async def query(
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
        Dict with ``results`` (list of knowledge unit dicts), ``source``
        ("local", "team", or "both"), and ``team`` (connectivity status:
        "not_configured", "ok", or "error" with message), or ``error``
        if inputs are invalid.
    """
    cleaned = [d.strip().lower() for d in domain if d.strip()]
    if not cleaned:
        return {"error": "At least one non-empty domain tag is required."}
    if limit < 1:
        return {"error": "limit must be a positive integer."}
    if limit > _MAX_QUERY_LIMIT:
        return {"error": f"limit must not exceed {_MAX_QUERY_LIMIT}."}

    store = _get_store()
    local_results = await asyncio.to_thread(
        store.query,
        cleaned,
        language=language,
        framework=framework,
        limit=limit,
    )

    team_units: list[KnowledgeUnit] | None = None
    team_status: dict[str, str]
    team_client = _get_team_client()
    if team_client is None:
        team_status = {"status": "not_configured"}
    else:
        team_result = await team_client.query(
            cleaned,
            language=language,
            framework=framework,
            limit=limit,
        )
        team_units = team_result.units
        if team_units is None:
            logger.info("Team API unavailable for query; using local results only.")
            team_status = {"status": "error", "error": team_result.error or "unknown"}
        else:
            team_status = {"status": "ok"}

    results, source = _merge_results(
        local_results,
        team_units,
        query_domains=cleaned,
        query_language=language,
        query_framework=framework,
        limit=limit,
    )
    for result in results:
        unit_id = result["id"]
        result["action_required"] = f'If you verify this, call confirm(unit_id="{unit_id}").'
    return {"results": results, "source": source, "team": team_status}


@mcp.tool(name="propose")
async def propose(
    summary: str,
    detail: str,
    action: str,
    domain: list[str],
    language: str | None = None,
    framework: str | None = None,
    pattern: str = "",
) -> dict:
    """Propose a new knowledge unit.

    Propose flow scenarios:
    - Team configured and reachable: store locally, then submit the same KU to team.
    - Team configured but unreachable: store locally and leave the KU pending sync.
    - Team configured but rejects the proposal: store locally and mark team sync rejected.
    - No team configured: always stores locally.

    Args:
        summary: Concise description of the insight.
        detail: Fuller explanation.
        action: Recommended action to take.
        domain: Domain tags for categorisation.
        language: Optional single programming language context.
        framework: Optional single framework context.
        pattern: Optional pattern name.

    Returns:
        Dict with ``id``, ``tier``, ``source``, ``sync_status``, and
        ``message``. Includes ``team`` status details when team sync is
        configured, or ``error`` if inputs are invalid.
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

    store = _get_store()
    team_client = _get_team_client()
    initial_sync_status = (
        TeamSyncStatus.NOT_APPLICABLE if team_client is None else TeamSyncStatus.PENDING
    )
    await asyncio.to_thread(store.insert, unit, team_sync_status=initial_sync_status)

    result = {
        "id": unit.id,
        "tier": unit.tier.value,
        "source": "local",
        "sync_status": initial_sync_status.value,
        "message": f"Knowledge unit {unit.id} stored locally.",
    }
    if team_client is None:
        return result

    attempted_at = datetime.now(UTC)
    try:
        team_unit = await team_client.propose(unit)
    except TeamRejectedError as exc:
        await asyncio.to_thread(
            store.update_team_sync_status,
            unit.id,
            TeamSyncStatus.REJECTED,
            error=exc.detail,
            attempted_at=attempted_at,
        )
        result["sync_status"] = TeamSyncStatus.REJECTED.value
        result["message"] = (
            f"Knowledge unit {unit.id} stored locally; team rejected the shared submission."
        )
        result["team"] = {"status": "rejected", "error": exc.detail}
        return result

    if team_unit is None:
        logger.warning("Team API unreachable after local write; leaving KU pending sync.")
        await asyncio.to_thread(
            store.update_team_sync_status,
            unit.id,
            TeamSyncStatus.PENDING,
            error="Team API unreachable during propose.",
            attempted_at=attempted_at,
        )
        result["sync_status"] = TeamSyncStatus.PENDING.value
        result["team"] = {"status": "error", "error": "Team API unreachable during propose."}
        result["message"] = (
            f"Knowledge unit {unit.id} stored locally; team sync is pending retry."
        )
        return result

    await asyncio.to_thread(
        store.update_team_sync_status,
        unit.id,
        TeamSyncStatus.SYNCED,
        error=None,
        attempted_at=attempted_at,
    )
    result["source"] = "both"
    result["sync_status"] = TeamSyncStatus.SYNCED.value
    result["team"] = {"status": "ok"}
    result["message"] = (
        f"Knowledge unit {unit.id} stored locally and submitted to team."
    )
    return result


@mcp.tool(name="confirm")
async def confirm(unit_id: str) -> dict:
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
    local_unit = await asyncio.to_thread(store.get, unit_id)

    if local_unit is not None:
        confirmed = apply_confirmation(local_unit)
        await asyncio.to_thread(store.update, confirmed)
        result: dict = {
            "id": confirmed.id,
            "new_confidence": confirmed.evidence.confidence,
            "confirmations": confirmed.evidence.confirmations,
            "source": "local",
        }
        # Best-effort propagation to team.
        team_client = _get_team_client()
        if team_client is not None:
            team_unit = await team_client.confirm(unit_id)
            if team_unit is not None:
                result["source"] = "both"
        return result

    # Not in local store — try team API.
    team_client = _get_team_client()
    if team_client is not None:
        team_unit = await team_client.confirm(unit_id)
        if team_unit is not None:
            return {
                "id": team_unit.id,
                "new_confidence": team_unit.evidence.confidence,
                "confirmations": team_unit.evidence.confirmations,
                "source": "team",
            }

    return {"error": f"Knowledge unit not found: {unit_id}"}


@mcp.tool(name="flag")
async def flag(unit_id: str, reason: str) -> dict:
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
    local_unit = await asyncio.to_thread(store.get, unit_id)

    if local_unit is not None:
        flagged = apply_flag(local_unit, flag_reason)
        await asyncio.to_thread(store.update, flagged)
        result: dict = {
            "id": flagged.id,
            "new_confidence": flagged.evidence.confidence,
            "message": f"Knowledge unit {flagged.id} flagged as {cleaned_reason}.",
            "source": "local",
        }
        # Best-effort propagation to team.
        team_client = _get_team_client()
        if team_client is not None:
            team_unit = await team_client.flag(unit_id, flag_reason)
            if team_unit is not None:
                result["source"] = "both"
        return result

    # Not in local store — try team API.
    team_client = _get_team_client()
    if team_client is not None:
        team_unit = await team_client.flag(unit_id, flag_reason)
        if team_unit is not None:
            return {
                "id": team_unit.id,
                "new_confidence": team_unit.evidence.confidence,
                "message": f"Knowledge unit {team_unit.id} flagged as {cleaned_reason}.",
                "source": "team",
            }

    return {"error": f"Knowledge unit not found: {unit_id}"}


@mcp.tool(name="reflect")
def reflect(session_context: str) -> dict:
    """Analyse session context for candidate knowledge units worth sharing.

    The agent passes its session conversation context. Returns candidates
    that may be worth proposing as knowledge units. Submit approved
    candidates individually via propose.

    This tool is a stub in the PoC. Session mining intelligence lives in
    the /cq:reflect slash command (issue #9).

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
        "message": "Session context received. Identify candidate knowledge units and submit each via propose.",
        "status": "stub",
    }


@mcp.tool(name="status")
async def status() -> dict:
    """Return knowledge store statistics and team API connectivity.

    Provides an overview of the local store: total knowledge unit count,
    domain tag breakdown, most recent additions, and confidence score
    distribution across defined buckets. Includes team API status.

    Returns:
        Dict with ``total_count``, ``domain_counts``, ``recent``
        (serialised knowledge units), ``confidence_distribution``, and
        ``team`` (connectivity status). Includes ``promoted_to_team``
        when pending KUs were synced at startup.
    """
    store = _get_store()
    stats = await asyncio.to_thread(store.stats)
    result = stats.model_dump(mode="json")
    if _drain_promoted_count is not None and _drain_promoted_count > 0:
        result["promoted_to_team"] = _drain_promoted_count

    team_client = _get_team_client()
    if team_client is None:
        result["team"] = {"status": "not_configured"}
    elif await team_client.health():
        result["team"] = {"status": "ok", "url": team_client.base_url}
    else:
        result["team"] = {"status": "unreachable", "url": team_client.base_url}

    return result


def main() -> None:
    """Start the cq MCP server."""
    mcp.run()
