"""Tests for the CRAIC MCP server tools."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from craic_mcp import server
from craic_mcp.knowledge_unit import (
    Context,
    Evidence,
    Insight,
    KnowledgeUnit,
    Tier,
    create_knowledge_unit,
)
from craic_mcp.server import (
    _MAX_QUERY_LIMIT,
    craic_confirm,
    craic_flag,
    craic_propose,
    craic_query,
    craic_reflect,
    craic_status,
)
from craic_mcp.team_client import TeamRejectedError


@pytest.fixture(autouse=True)
def _store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Provide a fresh local store and no team client for each test."""
    monkeypatch.setenv("CRAIC_LOCAL_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CRAIC_TEAM_ADDR", "")
    server._close_store()
    server._team_client = None
    server._drain_promoted_count = None
    yield
    server._close_store()
    server._team_client = None
    server._drain_promoted_count = None


async def _propose_unit(
    *,
    domain: list[str] | None = None,
    summary: str = "Use connection pooling",
    detail: str = "Database connections are expensive to create.",
    action: str = "Configure a pool with max size 10.",
    language: str | None = None,
    framework: str | None = None,
) -> dict:
    """Helper to propose a knowledge unit and return the result."""
    return await craic_propose(
        summary=summary,
        detail=detail,
        action=action,
        domain=domain or ["databases", "performance"],
        language=language,
        framework=framework,
    )


def _make_team_unit(
    *,
    unit_id: str = "ku_team_001",
    domain: list[str] | None = None,
    summary: str = "Team insight",
    confidence: float = 0.8,
) -> KnowledgeUnit:
    """Create a KnowledgeUnit that looks like it came from the team store."""
    return KnowledgeUnit(
        id=unit_id,
        domain=domain or ["api"],
        insight=Insight(summary=summary, detail="Detail.", action="Act."),
        context=Context(),
        evidence=Evidence(confidence=confidence, confirmations=3),
        tier=Tier.TEAM,
    )


class TestCraicQuery:
    async def test_query_returns_empty_for_no_data(self) -> None:
        result = await craic_query(domain=["databases"])
        assert result["results"] == []
        assert result["source"] == "local"

    async def test_query_returns_matching_units(self) -> None:
        await _propose_unit(domain=["databases"])
        result = await craic_query(domain=["databases"])
        assert len(result["results"]) == 1
        assert "databases" in result["results"][0]["domain"]

    async def test_query_results_include_confirm_reminder(self) -> None:
        proposed = await _propose_unit(domain=["databases"])
        result = await craic_query(domain=["databases"])
        returned = result["results"][0]
        assert "action_required" in returned
        assert proposed["id"] in returned["action_required"]
        assert "craic_confirm" in returned["action_required"]

    async def test_query_boosts_matching_language(self) -> None:
        await _propose_unit(domain=["web"], language="python")
        await _propose_unit(domain=["web"], language="go")
        result = await craic_query(domain=["web"], language="python")
        assert len(result["results"]) == 2
        assert "python" in result["results"][0]["context"]["languages"]

    async def test_query_boosts_matching_framework(self) -> None:
        await _propose_unit(domain=["web"], framework="fastapi")
        await _propose_unit(domain=["web"], framework="django")
        result = await craic_query(domain=["web"], framework="fastapi")
        assert len(result["results"]) == 2
        assert "fastapi" in result["results"][0]["context"]["frameworks"]

    async def test_query_respects_limit(self) -> None:
        for _ in range(3):
            await _propose_unit(domain=["api"])
        result = await craic_query(domain=["api"], limit=2)
        assert len(result["results"]) == 2

    async def test_query_no_match_returns_empty(self) -> None:
        await _propose_unit(domain=["databases"])
        result = await craic_query(domain=["networking"])
        assert result["results"] == []

    async def test_query_empty_domain_returns_error(self) -> None:
        result = await craic_query(domain=[])
        assert "error" in result

    async def test_query_zero_limit_returns_error(self) -> None:
        result = await craic_query(domain=["api"], limit=0)
        assert "error" in result

    async def test_query_negative_limit_returns_error(self) -> None:
        result = await craic_query(domain=["api"], limit=-1)
        assert "error" in result

    async def test_query_exceeding_max_limit_returns_error(self) -> None:
        result = await craic_query(domain=["api"], limit=_MAX_QUERY_LIMIT + 1)
        assert "error" in result
        assert str(_MAX_QUERY_LIMIT) in result["error"]

    async def test_query_whitespace_only_domains_returns_error(self) -> None:
        result = await craic_query(domain=["", "  "])
        assert "error" in result

    async def test_query_strips_whitespace_from_domains(self) -> None:
        await _propose_unit(domain=["databases"])
        result = await craic_query(domain=["  databases  "])
        assert len(result["results"]) == 1


class TestCraicQueryWithTeam:
    async def test_query_merges_local_and_team_results(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _propose_unit(domain=["api"])
        team_unit = _make_team_unit(domain=["api"])
        mock_client = MagicMock()
        mock_client.query = AsyncMock(return_value=[team_unit])
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = await craic_query(domain=["api"])
        assert len(result["results"]) == 2
        assert result["source"] == "both"

    async def test_query_deduplicates_by_id(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        proposed = await _propose_unit(domain=["api"])
        # Team returns a unit with the same ID as the local one.
        duplicate = _make_team_unit(
            unit_id=proposed["id"],
            domain=["api"],
        )
        mock_client = MagicMock()
        mock_client.query = AsyncMock(return_value=[duplicate])
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = await craic_query(domain=["api"])
        assert len(result["results"]) == 1
        # Local version takes precedence.
        assert result["results"][0]["tier"] == "local"
        # Source reflects that both stores were consulted.
        assert result["source"] == "both"

    async def test_query_team_only_results(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        team_unit = _make_team_unit(domain=["api"])
        mock_client = MagicMock()
        mock_client.query = AsyncMock(return_value=[team_unit])
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = await craic_query(domain=["api"])
        assert len(result["results"]) == 1
        assert result["source"] == "team"

    async def test_query_degrades_when_team_unreachable(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _propose_unit(domain=["api"])
        mock_client = MagicMock()
        mock_client.query = AsyncMock(return_value=None)
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = await craic_query(domain=["api"])
        assert len(result["results"]) == 1
        assert result["source"] == "local"

    async def test_query_respects_limit_across_merged_results(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _propose_unit(domain=["api"])
        await _propose_unit(domain=["api"])
        team_units = [
            _make_team_unit(unit_id="ku_team_1", domain=["api"]),
            _make_team_unit(unit_id="ku_team_2", domain=["api"]),
        ]
        mock_client = MagicMock()
        mock_client.query = AsyncMock(return_value=team_units)
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = await craic_query(domain=["api"], limit=3)
        assert len(result["results"]) == 3


class TestCraicPropose:
    async def test_propose_returns_id_and_tier(self) -> None:
        result = await _propose_unit()
        assert result["id"].startswith("ku_")
        assert result["tier"] == "local"
        assert "stored locally" in result["message"]

    async def test_propose_with_context(self) -> None:
        result = await _propose_unit(language="python", framework="fastapi")
        stored = await craic_query(domain=["databases"], language="python")
        assert len(stored["results"]) == 1
        assert "python" in stored["results"][0]["context"]["languages"]
        assert "fastapi" in stored["results"][0]["context"]["frameworks"]
        assert result["tier"] == "local"

    async def test_propose_blank_summary_returns_error(self) -> None:
        result = await craic_propose(
            summary="   ",
            detail="some detail",
            action="do something",
            domain=["api"],
        )
        assert "error" in result

    async def test_propose_blank_detail_returns_error(self) -> None:
        result = await craic_propose(
            summary="summary",
            detail="",
            action="do something",
            domain=["api"],
        )
        assert "error" in result

    async def test_propose_whitespace_only_domains_returns_error(self) -> None:
        result = await craic_propose(
            summary="summary",
            detail="detail",
            action="action",
            domain=["", "  "],
        )
        assert "error" in result

    async def test_propose_strips_whitespace_from_language(self) -> None:
        await _propose_unit(domain=["web"], language="  python  ")
        result = await craic_query(domain=["web"], language="python")
        assert len(result["results"]) == 1
        assert "python" in result["results"][0]["context"]["languages"]

    async def test_propose_strips_whitespace_from_framework(self) -> None:
        await _propose_unit(domain=["web"], framework="  fastapi  ")
        result = await craic_query(domain=["web"], framework="fastapi")
        assert len(result["results"]) == 1
        assert "fastapi" in result["results"][0]["context"]["frameworks"]

    async def test_propose_treats_whitespace_only_language_as_none(self) -> None:
        await _propose_unit(domain=["web"], language="   ")
        result = await craic_query(domain=["web"])
        assert result["results"][0]["context"]["languages"] == []

    async def test_propose_stores_retrievable_unit(self) -> None:
        result = await _propose_unit(domain=["testing"])
        confirmed = await craic_confirm(unit_id=result["id"])
        assert confirmed["id"] == result["id"]


class TestCraicProposeWithTeam:
    async def test_propose_pushes_to_team(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        team_unit = _make_team_unit(unit_id="ku_team_pushed")
        mock_client = MagicMock()
        mock_client.propose = AsyncMock(return_value=team_unit)
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = await _propose_unit(domain=["api"])
        assert result["id"] == "ku_team_pushed"
        assert result["tier"] == "team"
        assert "proposed to team" in result["message"]
        mock_client.propose.assert_called_once()

    async def test_propose_skips_local_store_when_team_succeeds(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        team_unit = _make_team_unit(unit_id="ku_team_only")
        mock_client = MagicMock()
        mock_client.propose = AsyncMock(return_value=team_unit)
        mock_client.query = AsyncMock(return_value=[])
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        await _propose_unit(domain=["api"])
        local_results = await craic_query(domain=["api"])
        assert len(local_results["results"]) == 0

    async def test_propose_returns_error_when_team_rejects(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_client = MagicMock()
        mock_client.propose = AsyncMock(side_effect=TeamRejectedError(422, "Invalid domain"))
        mock_client.query = AsyncMock(return_value=[])
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = await _propose_unit(domain=["api"])
        assert "error" in result
        assert "rejected" in result["error"].lower()
        local_results = await craic_query(domain=["api"])
        assert len(local_results["results"]) == 0

    async def test_propose_falls_back_to_local_when_team_unreachable(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_client = MagicMock()
        mock_client.propose = AsyncMock(return_value=None)
        mock_client.query = AsyncMock(return_value=[])
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = await _propose_unit(domain=["api"])
        assert result["id"].startswith("ku_")
        assert result["tier"] == "local"
        assert "stored locally" in result["message"]
        local_results = await craic_query(domain=["api"])
        assert len(local_results["results"]) == 1


class TestCraicConfirm:
    async def test_confirm_boosts_confidence(self) -> None:
        proposed = await _propose_unit()
        result = await craic_confirm(unit_id=proposed["id"])
        assert result["new_confidence"] == pytest.approx(0.6)
        assert result["confirmations"] == 2

    async def test_confirm_missing_unit_returns_error(self) -> None:
        result = await craic_confirm(unit_id="ku_nonexistent")
        assert "error" in result
        assert "not found" in result["error"].lower()


class TestCraicConfirmWithTeam:
    async def test_confirm_propagates_to_team(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        proposed = await _propose_unit()
        team_unit = _make_team_unit(unit_id=proposed["id"])
        mock_client = MagicMock()
        mock_client.confirm = AsyncMock(return_value=team_unit)
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = await craic_confirm(unit_id=proposed["id"])
        assert result["source"] == "both"
        mock_client.confirm.assert_called_once_with(proposed["id"])

    async def test_confirm_local_only_when_team_not_found(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        proposed = await _propose_unit()
        mock_client = MagicMock()
        mock_client.confirm = AsyncMock(return_value=None)
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = await craic_confirm(unit_id=proposed["id"])
        assert result["source"] == "local"

    async def test_confirm_team_only_unit(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        team_unit = _make_team_unit(unit_id="ku_team_only")
        confirmed_unit = team_unit.model_copy(
            update={
                "evidence": Evidence(confidence=0.9, confirmations=4),
            },
        )
        mock_client = MagicMock()
        mock_client.confirm = AsyncMock(return_value=confirmed_unit)
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = await craic_confirm(unit_id="ku_team_only")
        assert result["source"] == "team"
        assert result["new_confidence"] == pytest.approx(0.9)

    async def test_confirm_not_found_anywhere(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_client = MagicMock()
        mock_client.confirm = AsyncMock(return_value=None)
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = await craic_confirm(unit_id="ku_nowhere")
        assert "error" in result


class TestCraicFlag:
    async def test_flag_reduces_confidence(self) -> None:
        proposed = await _propose_unit()
        result = await craic_flag(unit_id=proposed["id"], reason="stale")
        assert result["new_confidence"] == pytest.approx(0.35)
        assert "flagged as stale" in result["message"]

    async def test_flag_missing_unit_returns_error(self) -> None:
        result = await craic_flag(unit_id="ku_nonexistent", reason="stale")
        assert "error" in result

    async def test_flag_normalises_reason_whitespace(self) -> None:
        proposed = await _propose_unit()
        result = await craic_flag(unit_id=proposed["id"], reason="  stale  ")
        assert result["new_confidence"] == pytest.approx(0.35)

    async def test_flag_normalises_reason_case(self) -> None:
        proposed = await _propose_unit()
        result = await craic_flag(unit_id=proposed["id"], reason="STALE")
        assert result["new_confidence"] == pytest.approx(0.35)

    async def test_flag_invalid_reason_returns_error(self) -> None:
        proposed = await _propose_unit()
        result = await craic_flag(unit_id=proposed["id"], reason="invalid")
        assert "error" in result
        assert "Invalid reason" in result["error"]


class TestCraicFlagWithTeam:
    async def test_flag_propagates_to_team(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        proposed = await _propose_unit()
        team_unit = _make_team_unit(unit_id=proposed["id"])
        mock_client = MagicMock()
        mock_client.flag = AsyncMock(return_value=team_unit)
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = await craic_flag(unit_id=proposed["id"], reason="stale")
        assert result["source"] == "both"

    async def test_flag_team_only_unit(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        team_unit = _make_team_unit(unit_id="ku_team_only")
        flagged_unit = team_unit.model_copy(
            update={
                "evidence": Evidence(confidence=0.65, confirmations=3),
            },
        )
        mock_client = MagicMock()
        mock_client.flag = AsyncMock(return_value=flagged_unit)
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = await craic_flag(unit_id="ku_team_only", reason="stale")
        assert result["source"] == "team"
        assert result["new_confidence"] == pytest.approx(0.65)

    async def test_flag_not_found_anywhere(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_client = MagicMock()
        mock_client.flag = AsyncMock(return_value=None)
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = await craic_flag(unit_id="ku_nowhere", reason="stale")
        assert "error" in result


class TestCraicReflect:
    def test_reflect_returns_candidates_structure(self) -> None:
        result = craic_reflect(session_context="I discovered a bug in the API.")
        assert "candidates" in result
        assert isinstance(result["candidates"], list)
        assert "message" in result
        assert result["status"] == "stub"

    def test_reflect_empty_context_returns_message(self) -> None:
        result = craic_reflect(session_context="   ")
        assert result["candidates"] == []
        assert "empty" in result["message"].lower()
        assert result["status"] == "stub"


class TestCraicStatus:
    async def test_status_empty_store(self) -> None:
        result = await craic_status()
        assert result["total_count"] == 0
        assert result["domain_counts"] == {}
        assert result["recent"] == []

    async def test_status_returns_statistics(self) -> None:
        await _propose_unit(domain=["api", "payments"])
        await _propose_unit(domain=["api", "databases"])
        await _propose_unit(domain=["databases"])
        result = await craic_status()
        assert result["total_count"] == 3
        assert result["domain_counts"]["api"] == 2
        assert result["domain_counts"]["databases"] == 2
        assert result["domain_counts"]["payments"] == 1
        assert len(result["recent"]) == 3
        assert "confidence_distribution" in result

    async def test_status_returns_confidence_distribution(self) -> None:
        await _propose_unit(domain=["api"])
        result = await craic_status()
        # Default confidence is 0.5, falls in "0.5-0.7" bucket.
        assert result["confidence_distribution"]["0.5-0.7"] == 1


class TestEndToEnd:
    async def test_propose_query_confirm_flag_lifecycle(self) -> None:
        # Propose a unit.
        proposed = await craic_propose(
            summary="Stripe returns 200 for rate limits",
            detail="Response body contains error object despite 200 status.",
            action="Always parse response body for error field.",
            domain=["api", "payments", "stripe"],
            language="python",
        )
        unit_id = proposed["id"]

        # Query returns it.
        results = await craic_query(domain=["api", "payments"], language="python")
        assert len(results["results"]) == 1
        assert results["results"][0]["evidence"]["confidence"] == 0.5

        # Confirm boosts confidence.
        confirmed = await craic_confirm(unit_id=unit_id)
        assert confirmed["new_confidence"] == pytest.approx(0.6)
        assert confirmed["confirmations"] == 2

        # Verify boosted confidence in query results.
        results = await craic_query(domain=["api", "payments"])
        assert results["results"][0]["evidence"]["confidence"] == pytest.approx(0.6)

        # Flag reduces confidence.
        flagged = await craic_flag(unit_id=unit_id, reason="stale")
        assert flagged["new_confidence"] == pytest.approx(0.45)

        # Verify flag in query results.
        results = await craic_query(domain=["api", "payments"])
        result = results["results"][0]
        assert result["evidence"]["confidence"] == pytest.approx(0.45)
        assert len(result["flags"]) == 1
        assert result["flags"][0]["reason"] == "stale"


def _make_local_unit(*, domain: list[str] | None = None) -> KnowledgeUnit:
    """Create a KnowledgeUnit with local tier for drain tests."""
    return create_knowledge_unit(
        domain=domain or ["api"],
        insight=Insight(summary="Local insight", detail="Detail.", action="Act."),
        context=Context(),
        tier=Tier.LOCAL,
    )


class TestDrainLocalToTeam:
    async def test_drain_promotes_local_kus_to_team(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Local KUs are proposed to team and deleted from local store."""
        store = server._get_store()
        unit = _make_local_unit(domain=["api"])
        store.insert(unit)

        team_unit = _make_team_unit(unit_id="ku_team_promoted")
        mock_client = AsyncMock()
        mock_client.propose.return_value = team_unit
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        await server._drain_local_to_team()

        assert store.all() == []
        assert server._drain_promoted_count == 1

    async def test_drain_skips_when_no_team_client(self) -> None:
        """Drain does nothing when team is not configured."""
        store = server._get_store()
        unit = _make_local_unit(domain=["api"])
        store.insert(unit)

        await server._drain_local_to_team()

        assert len(store.all()) == 1

    async def test_drain_keeps_unit_on_transport_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """KU stays local when team API is unreachable."""
        store = server._get_store()
        unit = _make_local_unit(domain=["api"])
        store.insert(unit)

        mock_client = AsyncMock()
        mock_client.propose.return_value = None
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        await server._drain_local_to_team()

        assert len(store.all()) == 1
        assert server._drain_promoted_count == 0

    async def test_drain_keeps_unit_on_rejection(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """KU stays local when team API rejects it."""
        store = server._get_store()
        unit = _make_local_unit(domain=["api"])
        store.insert(unit)

        mock_client = AsyncMock()
        mock_client.propose.side_effect = TeamRejectedError(422, "bad")
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        await server._drain_local_to_team()

        assert len(store.all()) == 1
        assert server._drain_promoted_count == 0

    async def test_drain_handles_mixed_results(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Some KUs promote, some fail — only promoted ones are deleted."""
        store = server._get_store()
        u1 = _make_local_unit(domain=["api"])
        u2 = _make_local_unit(domain=["databases"])
        store.insert(u1)
        store.insert(u2)

        team_unit = _make_team_unit(unit_id="ku_team_ok")
        mock_client = AsyncMock()
        # First call succeeds, second returns None (unreachable).
        mock_client.propose.side_effect = [team_unit, None]
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        await server._drain_local_to_team()

        remaining = store.all()
        assert len(remaining) == 1
        assert server._drain_promoted_count == 1


class TestCraicStatusWithDrain:
    async def test_status_includes_promotion_count(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(server, "_drain_promoted_count", 3)
        result = await craic_status()
        assert result["promoted_to_team"] == 3

    async def test_status_omits_promotion_count_when_zero(self) -> None:
        result = await craic_status()
        assert "promoted_to_team" not in result

    async def test_status_omits_promotion_count_when_none(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(server, "_drain_promoted_count", None)
        result = await craic_status()
        assert "promoted_to_team" not in result
