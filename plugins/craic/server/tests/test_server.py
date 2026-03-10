"""Tests for the CRAIC MCP server tools."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from craic_mcp import server
from craic_mcp.knowledge_unit import (
    Context,
    Evidence,
    Insight,
    KnowledgeUnit,
    Tier,
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


@pytest.fixture(autouse=True)
def _store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Provide a fresh local store and no team client for each test."""
    monkeypatch.setenv("CRAIC_LOCAL_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CRAIC_TEAM_ADDR", "")
    server._close_store()
    server._close_team_client()
    yield
    server._close_store()
    server._close_team_client()


def _propose_unit(
    *,
    domain: list[str] | None = None,
    summary: str = "Use connection pooling",
    detail: str = "Database connections are expensive to create.",
    action: str = "Configure a pool with max size 10.",
    language: str | None = None,
    framework: str | None = None,
) -> dict:
    """Helper to propose a knowledge unit and return the result."""
    return craic_propose(
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
    def test_query_returns_empty_for_no_data(self) -> None:
        result = craic_query(domain=["databases"])
        assert result["results"] == []
        assert result["source"] == "local"

    def test_query_returns_matching_units(self) -> None:
        _propose_unit(domain=["databases"])
        result = craic_query(domain=["databases"])
        assert len(result["results"]) == 1
        assert "databases" in result["results"][0]["domain"]

    def test_query_filters_by_language(self) -> None:
        _propose_unit(domain=["web"], language="python")
        _propose_unit(domain=["web"], language="go")
        result = craic_query(domain=["web"], language="python")
        assert len(result["results"]) == 1
        assert "python" in result["results"][0]["context"]["languages"]

    def test_query_filters_by_framework(self) -> None:
        _propose_unit(domain=["web"], framework="fastapi")
        _propose_unit(domain=["web"], framework="django")
        result = craic_query(domain=["web"], framework="fastapi")
        assert len(result["results"]) == 1
        assert "fastapi" in result["results"][0]["context"]["frameworks"]

    def test_query_respects_limit(self) -> None:
        for _ in range(3):
            _propose_unit(domain=["api"])
        result = craic_query(domain=["api"], limit=2)
        assert len(result["results"]) == 2

    def test_query_no_match_returns_empty(self) -> None:
        _propose_unit(domain=["databases"])
        result = craic_query(domain=["networking"])
        assert result["results"] == []

    def test_query_empty_domain_returns_error(self) -> None:
        result = craic_query(domain=[])
        assert "error" in result

    def test_query_zero_limit_returns_error(self) -> None:
        result = craic_query(domain=["api"], limit=0)
        assert "error" in result

    def test_query_negative_limit_returns_error(self) -> None:
        result = craic_query(domain=["api"], limit=-1)
        assert "error" in result

    def test_query_exceeding_max_limit_returns_error(self) -> None:
        result = craic_query(domain=["api"], limit=_MAX_QUERY_LIMIT + 1)
        assert "error" in result
        assert str(_MAX_QUERY_LIMIT) in result["error"]

    def test_query_whitespace_only_domains_returns_error(self) -> None:
        result = craic_query(domain=["", "  "])
        assert "error" in result

    def test_query_strips_whitespace_from_domains(self) -> None:
        _propose_unit(domain=["databases"])
        result = craic_query(domain=["  databases  "])
        assert len(result["results"]) == 1


class TestCraicQueryWithTeam:
    def test_query_merges_local_and_team_results(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _propose_unit(domain=["api"])
        team_unit = _make_team_unit(domain=["api"])
        mock_client = MagicMock()
        mock_client.query.return_value = [team_unit]
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = craic_query(domain=["api"])
        assert len(result["results"]) == 2
        assert result["source"] == "both"

    def test_query_deduplicates_by_id(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        proposed = _propose_unit(domain=["api"])
        # Team returns a unit with the same ID as the local one.
        duplicate = _make_team_unit(
            unit_id=proposed["id"],
            domain=["api"],
        )
        mock_client = MagicMock()
        mock_client.query.return_value = [duplicate]
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = craic_query(domain=["api"])
        assert len(result["results"]) == 1
        # Local version takes precedence.
        assert result["results"][0]["tier"] == "local"
        # Source reflects that both stores were consulted.
        assert result["source"] == "both"

    def test_query_team_only_results(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        team_unit = _make_team_unit(domain=["api"])
        mock_client = MagicMock()
        mock_client.query.return_value = [team_unit]
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = craic_query(domain=["api"])
        assert len(result["results"]) == 1
        assert result["source"] == "team"

    def test_query_degrades_when_team_unreachable(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _propose_unit(domain=["api"])
        mock_client = MagicMock()
        mock_client.query.return_value = None
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = craic_query(domain=["api"])
        assert len(result["results"]) == 1
        assert result["source"] == "local"

    def test_query_respects_limit_across_merged_results(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _propose_unit(domain=["api"])
        _propose_unit(domain=["api"])
        team_units = [
            _make_team_unit(unit_id="ku_team_1", domain=["api"]),
            _make_team_unit(unit_id="ku_team_2", domain=["api"]),
        ]
        mock_client = MagicMock()
        mock_client.query.return_value = team_units
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = craic_query(domain=["api"], limit=3)
        assert len(result["results"]) == 3


class TestCraicPropose:
    def test_propose_returns_id_and_tier(self) -> None:
        result = _propose_unit()
        assert result["id"].startswith("ku_")
        assert result["tier"] == "local"
        assert "stored locally" in result["message"]

    def test_propose_with_context(self) -> None:
        result = _propose_unit(language="python", framework="fastapi")
        stored = craic_query(domain=["databases"], language="python")
        assert len(stored["results"]) == 1
        assert "python" in stored["results"][0]["context"]["languages"]
        assert "fastapi" in stored["results"][0]["context"]["frameworks"]
        assert result["tier"] == "local"

    def test_propose_blank_summary_returns_error(self) -> None:
        result = craic_propose(
            summary="   ",
            detail="some detail",
            action="do something",
            domain=["api"],
        )
        assert "error" in result

    def test_propose_blank_detail_returns_error(self) -> None:
        result = craic_propose(
            summary="summary",
            detail="",
            action="do something",
            domain=["api"],
        )
        assert "error" in result

    def test_propose_whitespace_only_domains_returns_error(self) -> None:
        result = craic_propose(
            summary="summary",
            detail="detail",
            action="action",
            domain=["", "  "],
        )
        assert "error" in result

    def test_propose_strips_whitespace_from_language(self) -> None:
        _propose_unit(domain=["web"], language="  python  ")
        result = craic_query(domain=["web"], language="python")
        assert len(result["results"]) == 1
        assert "python" in result["results"][0]["context"]["languages"]

    def test_propose_strips_whitespace_from_framework(self) -> None:
        _propose_unit(domain=["web"], framework="  fastapi  ")
        result = craic_query(domain=["web"], framework="fastapi")
        assert len(result["results"]) == 1
        assert "fastapi" in result["results"][0]["context"]["frameworks"]

    def test_propose_treats_whitespace_only_language_as_none(self) -> None:
        _propose_unit(domain=["web"], language="   ")
        result = craic_query(domain=["web"])
        assert result["results"][0]["context"]["languages"] == []

    def test_propose_stores_retrievable_unit(self) -> None:
        result = _propose_unit(domain=["testing"])
        confirmed = craic_confirm(unit_id=result["id"])
        assert confirmed["id"] == result["id"]


class TestCraicProposeWithTeam:
    def test_propose_pushes_to_team(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        team_unit = _make_team_unit(unit_id="ku_team_pushed")
        mock_client = MagicMock()
        mock_client.propose.return_value = team_unit
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = _propose_unit(domain=["api"])
        assert result["team_id"] == "ku_team_pushed"
        assert "shared to team" in result["message"]
        mock_client.propose.assert_called_once()

    def test_propose_succeeds_when_team_unreachable(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_client = MagicMock()
        mock_client.propose.return_value = None
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = _propose_unit(domain=["api"])
        assert result["id"].startswith("ku_")
        assert "team_id" not in result


class TestCraicConfirm:
    def test_confirm_boosts_confidence(self) -> None:
        proposed = _propose_unit()
        result = craic_confirm(unit_id=proposed["id"])
        assert result["new_confidence"] == pytest.approx(0.6)
        assert result["confirmations"] == 2

    def test_confirm_missing_unit_returns_error(self) -> None:
        result = craic_confirm(unit_id="ku_nonexistent")
        assert "error" in result
        assert "not found" in result["error"].lower()


class TestCraicConfirmWithTeam:
    def test_confirm_propagates_to_team(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        proposed = _propose_unit()
        team_unit = _make_team_unit(unit_id=proposed["id"])
        mock_client = MagicMock()
        mock_client.confirm.return_value = team_unit
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = craic_confirm(unit_id=proposed["id"])
        assert result["source"] == "both"
        mock_client.confirm.assert_called_once_with(proposed["id"])

    def test_confirm_local_only_when_team_not_found(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        proposed = _propose_unit()
        mock_client = MagicMock()
        mock_client.confirm.return_value = None
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = craic_confirm(unit_id=proposed["id"])
        assert result["source"] == "local"

    def test_confirm_team_only_unit(
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
        mock_client.confirm.return_value = confirmed_unit
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = craic_confirm(unit_id="ku_team_only")
        assert result["source"] == "team"
        assert result["new_confidence"] == pytest.approx(0.9)

    def test_confirm_not_found_anywhere(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_client = MagicMock()
        mock_client.confirm.return_value = None
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = craic_confirm(unit_id="ku_nowhere")
        assert "error" in result


class TestCraicFlag:
    def test_flag_reduces_confidence(self) -> None:
        proposed = _propose_unit()
        result = craic_flag(unit_id=proposed["id"], reason="stale")
        assert result["new_confidence"] == pytest.approx(0.35)
        assert "flagged as stale" in result["message"]

    def test_flag_missing_unit_returns_error(self) -> None:
        result = craic_flag(unit_id="ku_nonexistent", reason="stale")
        assert "error" in result

    def test_flag_normalises_reason_whitespace(self) -> None:
        proposed = _propose_unit()
        result = craic_flag(unit_id=proposed["id"], reason="  stale  ")
        assert result["new_confidence"] == pytest.approx(0.35)

    def test_flag_normalises_reason_case(self) -> None:
        proposed = _propose_unit()
        result = craic_flag(unit_id=proposed["id"], reason="STALE")
        assert result["new_confidence"] == pytest.approx(0.35)

    def test_flag_invalid_reason_returns_error(self) -> None:
        proposed = _propose_unit()
        result = craic_flag(unit_id=proposed["id"], reason="invalid")
        assert "error" in result
        assert "Invalid reason" in result["error"]


class TestCraicFlagWithTeam:
    def test_flag_propagates_to_team(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        proposed = _propose_unit()
        team_unit = _make_team_unit(unit_id=proposed["id"])
        mock_client = MagicMock()
        mock_client.flag.return_value = team_unit
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = craic_flag(unit_id=proposed["id"], reason="stale")
        assert result["source"] == "both"

    def test_flag_team_only_unit(
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
        mock_client.flag.return_value = flagged_unit
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = craic_flag(unit_id="ku_team_only", reason="stale")
        assert result["source"] == "team"
        assert result["new_confidence"] == pytest.approx(0.65)

    def test_flag_not_found_anywhere(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_client = MagicMock()
        mock_client.flag.return_value = None
        monkeypatch.setattr(server, "_get_team_client", lambda: mock_client)

        result = craic_flag(unit_id="ku_nowhere", reason="stale")
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
    def test_status_empty_store(self) -> None:
        result = craic_status()
        assert result["total_count"] == 0
        assert result["domain_counts"] == {}
        assert result["recent"] == []

    def test_status_returns_statistics(self) -> None:
        _propose_unit(domain=["api", "payments"])
        _propose_unit(domain=["api", "databases"])
        _propose_unit(domain=["databases"])
        result = craic_status()
        assert result["total_count"] == 3
        assert result["domain_counts"]["api"] == 2
        assert result["domain_counts"]["databases"] == 2
        assert result["domain_counts"]["payments"] == 1
        assert len(result["recent"]) == 3
        assert "confidence_distribution" in result

    def test_status_returns_confidence_distribution(self) -> None:
        _propose_unit(domain=["api"])
        result = craic_status()
        # Default confidence is 0.5, falls in "0.5-0.7" bucket.
        assert result["confidence_distribution"]["0.5-0.7"] == 1


class TestEndToEnd:
    def test_propose_query_confirm_flag_lifecycle(self) -> None:
        # Propose a unit.
        proposed = craic_propose(
            summary="Stripe returns 200 for rate limits",
            detail="Response body contains error object despite 200 status.",
            action="Always parse response body for error field.",
            domain=["api", "payments", "stripe"],
            language="python",
        )
        unit_id = proposed["id"]

        # Query returns it.
        results = craic_query(domain=["api", "payments"], language="python")
        assert len(results["results"]) == 1
        assert results["results"][0]["evidence"]["confidence"] == 0.5

        # Confirm boosts confidence.
        confirmed = craic_confirm(unit_id=unit_id)
        assert confirmed["new_confidence"] == pytest.approx(0.6)
        assert confirmed["confirmations"] == 2

        # Verify boosted confidence in query results.
        results = craic_query(domain=["api", "payments"])
        assert results["results"][0]["evidence"]["confidence"] == pytest.approx(0.6)

        # Flag reduces confidence.
        flagged = craic_flag(unit_id=unit_id, reason="stale")
        assert flagged["new_confidence"] == pytest.approx(0.45)

        # Verify flag in query results.
        results = craic_query(domain=["api", "payments"])
        result = results["results"][0]
        assert result["evidence"]["confidence"] == pytest.approx(0.45)
        assert len(result["flags"]) == 1
        assert result["flags"][0]["reason"] == "stale"
