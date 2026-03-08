"""Tests for the CRAIC Team API client."""

from collections.abc import Iterator

import httpx
import pytest
from craic_mcp.knowledge_unit import (
    Context,
    Evidence,
    FlagReason,
    Insight,
    KnowledgeUnit,
    Tier,
)
from craic_mcp.team_client import TeamClient

_MOCK_REQUEST = httpx.Request("GET", "http://test")


def _sample_unit(unit_id: str = "ku_test_001") -> KnowledgeUnit:
    """Create a sample knowledge unit for testing."""
    return KnowledgeUnit(
        id=unit_id,
        domain=["api", "payments"],
        insight=Insight(
            summary="Test insight",
            detail="Test detail.",
            action="Test action.",
        ),
        context=Context(languages=["python"]),
        evidence=Evidence(confidence=0.8, confirmations=3),
        tier=Tier.TEAM,
    )


def _mock_response(status_code: int, json: object) -> httpx.Response:
    """Create an httpx Response with a mock request attached."""
    return httpx.Response(
        status_code=status_code,
        json=json,
        request=_MOCK_REQUEST,
    )


def _raise_connect_error(*_args: object, **_kwargs: object) -> None:
    """Raise an httpx.ConnectError to simulate a connection failure."""
    raise httpx.ConnectError("Connection refused")


@pytest.fixture
def client() -> Iterator[TeamClient]:
    """Provide a TeamClient that is closed after the test."""
    c = TeamClient(base_url="http://localhost:8742")
    yield c
    c.close()


class TestTeamClientContextManager:
    def test_context_manager_closes_client(self) -> None:
        with TeamClient(base_url="http://localhost:8742") as client:
            assert client is not None
        assert client._client.is_closed


class TestTeamClientHealth:
    def test_health_returns_true_on_success(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        response = _mock_response(200, {"status": "ok"})
        monkeypatch.setattr(client._client, "get", lambda *_a, **_kw: response)
        assert client.health() is True

    def test_health_returns_false_on_connection_error(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(client._client, "get", _raise_connect_error)
        assert client.health() is False


class TestTeamClientQuery:
    def test_query_returns_none_on_connection_error(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(client._client, "get", _raise_connect_error)
        assert client.query(["api"]) is None

    def test_query_returns_none_on_invalid_json(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        response = httpx.Response(
            status_code=200,
            content=b"not json",
            request=_MOCK_REQUEST,
        )
        monkeypatch.setattr(client._client, "get", lambda *_a, **_kw: response)
        assert client.query(["api"]) is None

    def test_query_parses_response(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        unit = _sample_unit()
        response = _mock_response(200, [unit.model_dump(mode="json")])
        monkeypatch.setattr(client._client, "get", lambda *_a, **_kw: response)

        result = client.query(["api"])
        assert result is not None
        assert len(result) == 1
        assert result[0].id == unit.id


class TestTeamClientPropose:
    def test_propose_returns_none_on_connection_error(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(client._client, "post", _raise_connect_error)
        assert client.propose(_sample_unit()) is None

    def test_propose_parses_response(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        team_unit = _sample_unit(unit_id="ku_team_new")
        response = _mock_response(201, team_unit.model_dump(mode="json"))
        monkeypatch.setattr(client._client, "post", lambda *_a, **_kw: response)

        result = client.propose(_sample_unit())
        assert result is not None
        assert result.id == "ku_team_new"


class TestTeamClientConfirm:
    def test_confirm_returns_none_on_connection_error(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(client._client, "post", _raise_connect_error)
        assert client.confirm("ku_test") is None

    def test_confirm_returns_none_on_404(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        response = _mock_response(404, {"detail": "Not found"})
        monkeypatch.setattr(client._client, "post", lambda *_a, **_kw: response)
        assert client.confirm("ku_missing") is None

    def test_confirm_parses_response(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        unit = _sample_unit()
        response = _mock_response(200, unit.model_dump(mode="json"))
        monkeypatch.setattr(client._client, "post", lambda *_a, **_kw: response)

        result = client.confirm("ku_test_001")
        assert result is not None
        assert result.id == "ku_test_001"


class TestTeamClientFlag:
    def test_flag_returns_none_on_connection_error(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(client._client, "post", _raise_connect_error)
        assert client.flag("ku_test", FlagReason.STALE) is None

    def test_flag_returns_none_on_404(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        response = _mock_response(404, {"detail": "Not found"})
        monkeypatch.setattr(client._client, "post", lambda *_a, **_kw: response)
        assert client.flag("ku_missing", FlagReason.INCORRECT) is None

    def test_flag_parses_response(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        unit = _sample_unit()
        response = _mock_response(200, unit.model_dump(mode="json"))
        monkeypatch.setattr(client._client, "post", lambda *_a, **_kw: response)

        result = client.flag("ku_test_001", FlagReason.DUPLICATE)
        assert result is not None
        assert result.id == "ku_test_001"
