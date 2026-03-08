"""Tests for the CRAIC MCP server tools."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from craic_mcp import server
from craic_mcp.server import (
    craic_confirm,
    craic_flag,
    craic_propose,
    craic_query,
    craic_reflect,
)


@pytest.fixture(autouse=True)
def _store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Provide a fresh local store for each test."""
    monkeypatch.setenv("CRAIC_LOCAL_DB_PATH", str(tmp_path / "test.db"))
    server._store = None
    yield
    server._close_store()


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

    def test_query_whitespace_only_domains_returns_error(self) -> None:
        result = craic_query(domain=["", "  "])
        assert "error" in result

    def test_query_strips_whitespace_from_domains(self) -> None:
        _propose_unit(domain=["databases"])
        result = craic_query(domain=["  databases  "])
        assert len(result["results"]) == 1


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

    def test_propose_stores_retrievable_unit(self) -> None:
        result = _propose_unit(domain=["testing"])
        confirmed = craic_confirm(unit_id=result["id"])
        assert confirmed["id"] == result["id"]


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


class TestCraicFlag:
    def test_flag_reduces_confidence(self) -> None:
        proposed = _propose_unit()
        result = craic_flag(unit_id=proposed["id"], reason="stale")
        assert result["new_confidence"] == pytest.approx(0.35)
        assert "flagged as stale" in result["message"]

    def test_flag_missing_unit_returns_error(self) -> None:
        result = craic_flag(unit_id="ku_nonexistent", reason="stale")
        assert "error" in result

    def test_flag_invalid_reason_returns_error(self) -> None:
        proposed = _propose_unit()
        result = craic_flag(unit_id=proposed["id"], reason="invalid")
        assert "error" in result
        assert "Invalid reason" in result["error"]


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
