"""Tests for the cq Team API client."""

from collections.abc import AsyncIterator

import httpx
import pytest
from cq_mcp.knowledge_unit import (
    Context,
    Evidence,
    FlagReason,
    Insight,
    KnowledgeUnit,
    Tier,
)
from cq_mcp.team_client import TeamClient

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


async def _raise_connect_error(*_args: object, **_kwargs: object) -> None:
    """Raise an httpx.ConnectError to simulate a connection failure."""
    raise httpx.ConnectError("Connection refused")


def _async_returning(response: httpx.Response):
    """Create an async callable that returns a fixed response."""

    async def handler(*_args: object, **_kwargs: object) -> httpx.Response:
        return response

    return handler


@pytest.fixture
async def client() -> AsyncIterator[TeamClient]:
    """Provide a TeamClient that is closed after the test."""
    c = TeamClient(base_url="http://localhost:8742")
    yield c
    await c.close()


class TestTeamClientBaseUrl:
    async def test_base_url_returns_configured_url(self) -> None:
        async with TeamClient(base_url="http://localhost:8742") as client:
            assert client.base_url == "http://localhost:8742"


class TestTeamClientContextManager:
    async def test_context_manager_closes_client(self) -> None:
        async with TeamClient(base_url="http://localhost:8742") as client:
            assert client is not None
        assert client._client.is_closed


class TestTeamClientHealth:
    async def test_health_returns_true_on_success(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        response = _mock_response(200, {"status": "ok"})
        monkeypatch.setattr(client._client, "get", _async_returning(response))
        assert await client.health() is True

    async def test_health_returns_false_on_connection_error(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(client._client, "get", _raise_connect_error)
        assert await client.health() is False


class TestTeamClientQuery:
    async def test_query_returns_error_on_connection_error(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(client._client, "get", _raise_connect_error)
        result = await client.query(["api"])
        assert result.units is None
        assert result.error is not None
        assert "Connection refused" in result.error

    async def test_query_returns_error_on_invalid_json(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        response = httpx.Response(
            status_code=200,
            content=b"not json",
            request=_MOCK_REQUEST,
        )
        monkeypatch.setattr(client._client, "get", _async_returning(response))
        result = await client.query(["api"])
        assert result.units is None
        assert result.error is not None

    async def test_query_parses_response(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        unit = _sample_unit()
        response = _mock_response(200, [unit.model_dump(mode="json")])
        monkeypatch.setattr(client._client, "get", _async_returning(response))

        result = await client.query(["api"])
        assert result.units is not None
        assert result.error is None
        assert len(result.units) == 1
        assert result.units[0].id == unit.id


class TestTeamClientPropose:
    async def test_propose_returns_none_on_connection_error(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(client._client, "post", _raise_connect_error)
        assert await client.propose(_sample_unit()) is None

    async def test_propose_raises_on_http_rejection(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from cq_mcp.team_client import TeamRejectedError

        response = _mock_response(422, {"detail": "Invalid domain"})
        monkeypatch.setattr(client._client, "post", _async_returning(response))

        with pytest.raises(TeamRejectedError) as exc_info:
            await client.propose(_sample_unit())
        assert exc_info.value.status_code == 422

    async def test_propose_parses_response(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        team_unit = _sample_unit(unit_id="ku_team_new")
        response = _mock_response(201, team_unit.model_dump(mode="json"))
        monkeypatch.setattr(client._client, "post", _async_returning(response))

        result = await client.propose(_sample_unit())
        assert result is not None
        assert result.id == "ku_team_new"

    async def test_propose_sends_id_and_evidence(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict[str, object] = {}
        unit = _sample_unit(unit_id="ku_supplied")

        async def handler(*_args: object, **kwargs: object) -> httpx.Response:
            captured.update(kwargs)
            return _mock_response(201, unit.model_dump(mode="json"))

        monkeypatch.setattr(client._client, "post", handler)

        await client.propose(unit)

        assert captured["json"]["id"] == "ku_supplied"
        assert captured["json"]["evidence"]["confidence"] == unit.evidence.confidence


class TestTeamClientConfirm:
    async def test_confirm_returns_none_on_connection_error(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(client._client, "post", _raise_connect_error)
        assert await client.confirm("ku_test") is None

    async def test_confirm_returns_none_on_404(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        response = _mock_response(404, {"detail": "Not found"})
        monkeypatch.setattr(client._client, "post", _async_returning(response))
        assert await client.confirm("ku_missing") is None

    async def test_confirm_parses_response(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        unit = _sample_unit()
        response = _mock_response(200, unit.model_dump(mode="json"))
        monkeypatch.setattr(client._client, "post", _async_returning(response))

        result = await client.confirm("ku_test_001")
        assert result is not None
        assert result.id == "ku_test_001"


class TestTeamClientFlag:
    async def test_flag_returns_none_on_connection_error(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(client._client, "post", _raise_connect_error)
        assert await client.flag("ku_test", FlagReason.STALE) is None

    async def test_flag_returns_none_on_404(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        response = _mock_response(404, {"detail": "Not found"})
        monkeypatch.setattr(client._client, "post", _async_returning(response))
        assert await client.flag("ku_missing", FlagReason.INCORRECT) is None

    async def test_flag_parses_response(
        self,
        client: TeamClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        unit = _sample_unit()
        response = _mock_response(200, unit.model_dump(mode="json"))
        monkeypatch.setattr(client._client, "post", _async_returning(response))

        result = await client.flag("ku_test_001", FlagReason.DUPLICATE)
        assert result is not None
        assert result.id == "ku_test_001"
