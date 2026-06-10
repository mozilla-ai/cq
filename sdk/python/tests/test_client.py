"""Tests for Client."""

import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from cq.client import Client, FallbackError, RemoteError
from cq.models import FlagReason, Tier
from cq.store import StoreStats


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[Client]:
    c = Client(local_db_path=tmp_path / "test.db")
    yield c
    c.close()


class TestClientLogger:
    def test_silent_by_default(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        with caplog.at_level(logging.DEBUG):
            c = Client(local_db_path=tmp_path / "test.db")
            c.close()
        assert caplog.records == []
        cq_logger = logging.getLogger("cq")
        assert any(isinstance(h, logging.NullHandler) for h in cq_logger.handlers)

    def test_accepts_caller_supplied_logger(self, tmp_path: Path):
        supplied = logging.getLogger("test.cq.caller")
        c = Client(local_db_path=tmp_path / "test.db", logger=supplied)
        assert c._logger is supplied
        c.close()

    def test_default_logger_is_cq_client(self, tmp_path: Path):
        c = Client(local_db_path=tmp_path / "test.db")
        assert c._logger.name == "cq.client"
        c.close()


class TestLocalOnlyMode:
    def test_no_remote_addr_by_default(self, client: Client):
        assert client.addr is None

    def test_propose_and_query_roundtrip(self, client: Client):
        ku = client.propose(
            summary="Use connection pooling",
            detail="Connections are expensive.",
            action="Configure pool max size.",
            domains=["databases"],
        )
        assert ku.id.startswith("ku_")

        result = client.query(["databases"])
        assert result.source == "local"
        assert result.warnings == []
        assert len(result.units) == 1
        assert result.units[0].id == ku.id

    def test_confirm_boosts_confidence(self, client: Client):
        ku = client.propose(
            summary="Test insight",
            detail="Detail.",
            action="Action.",
            domains=["testing"],
        )
        confirmed = client.confirm(ku.id)
        assert confirmed.evidence.confidence == pytest.approx(0.6)
        assert confirmed.evidence.confirmations == 2

    def test_flag_reduces_confidence(self, client: Client):
        ku = client.propose(
            summary="Test insight",
            detail="Detail.",
            action="Action.",
            domains=["testing"],
        )
        flagged = client.flag(ku.id, FlagReason.STALE)
        assert flagged.evidence.confidence == pytest.approx(0.35)
        assert len(flagged.flags) == 1
        assert flagged.flags[0].reason == FlagReason.STALE

    def test_confirm_missing_unit_raises(self, client: Client):
        with pytest.raises(KeyError, match="ku_ffffffffffffffffffffffffffffffff"):
            client.confirm("ku_ffffffffffffffffffffffffffffffff")

    def test_flag_missing_unit_raises(self, client: Client):
        with pytest.raises(KeyError, match="ku_ffffffffffffffffffffffffffffffff"):
            client.flag("ku_ffffffffffffffffffffffffffffffff", FlagReason.STALE)

    def test_status_returns_store_stats(self, client: Client):
        client.propose(
            summary="Test",
            detail="Detail.",
            action="Action.",
            domains=["api"],
        )
        stats = client.status()
        assert stats.total_count == 1
        assert "api" in stats.domain_counts

    def test_status_local_only_has_tier_counts(self, client: Client):
        client.propose(
            summary="Test",
            detail="Detail.",
            action="Action.",
            domains=["api"],
        )
        stats = client.status()
        assert stats.tier_counts == {Tier.LOCAL: 1}

    def test_drain_raises_without_remote(self, client: Client):
        with pytest.raises(RuntimeError, match="No remote API configured"):
            client.drain()

    def test_context_manager(self, tmp_path: Path):
        with Client(local_db_path=tmp_path / "test.db") as c:
            ku = c.propose(
                summary="Test",
                detail="Detail.",
                action="Action.",
                domains=["testing"],
            )
            assert c.query(["testing"]).units[0].id == ku.id

    def test_propose_with_single_language_and_framework(self, client: Client):
        ku = client.propose(
            summary="Use Django ORM",
            detail="Better than raw SQL.",
            action="Use QuerySet API.",
            domains=["databases"],
            languages=["python"],
            frameworks=["django"],
        )
        assert ku.context.languages == ["python"]
        assert ku.context.frameworks == ["django"]

    def test_propose_with_multiple_languages_and_frameworks(self, client: Client):
        ku = client.propose(
            summary="Cross-language insight",
            detail="Applies to both Python and Go.",
            action="Check both implementations.",
            domains=["api"],
            languages=["python", "go"],
            frameworks=["fastapi", "grpc"],
        )
        assert ku.context.languages == ["python", "go"]
        assert ku.context.frameworks == ["fastapi", "grpc"]

    def test_confirm_non_local_without_remote_raises(self, client: Client):
        with pytest.raises(RuntimeError, match="remote API"):
            client.confirm("ku_ffffffffffffffffffffffffffffffff", tier=Tier.PRIVATE)

    def test_flag_non_local_without_remote_raises(self, client: Client):
        with pytest.raises(RuntimeError, match="remote API"):
            client.flag("ku_ffffffffffffffffffffffffffffffff", FlagReason.STALE, tier=Tier.PRIVATE)

    def test_query_bare_string_domains_coerced_to_list(self, client: Client):
        client.propose(
            summary="Bare string test",
            detail="Detail.",
            action="Action.",
            domains=["api"],
        )
        result = client.query("api")  # type: ignore[arg-type]
        assert len(result.units) == 1

    def test_query_bare_string_languages_coerced_to_list(self, client: Client):
        client.propose(
            summary="Python insight",
            detail="Detail.",
            action="Action.",
            domains=["api"],
            languages=["python"],
        )
        result = client.query(["api"], languages="python")  # type: ignore[arg-type]
        assert len(result.units) == 1
        assert result.units[0].context.languages == ["python"]

    def test_query_bare_string_frameworks_coerced_to_list(self, client: Client):
        client.propose(
            summary="Django insight",
            detail="Detail.",
            action="Action.",
            domains=["web"],
            frameworks=["django"],
        )
        result = client.query(["web"], frameworks="django")  # type: ignore[arg-type]
        assert len(result.units) == 1
        assert result.units[0].context.frameworks == ["django"]

    def test_propose_bare_string_domains_coerced_to_list(self, client: Client):
        ku = client.propose(
            summary="Single domain",
            detail="Detail.",
            action="Action.",
            domains="api",  # type: ignore[arg-type]
        )
        assert ku.domains == ["api"]

    def test_propose_bare_string_languages_coerced_to_list(self, client: Client):
        ku = client.propose(
            summary="Single lang",
            detail="Detail.",
            action="Action.",
            domains=["api"],
            languages="python",  # type: ignore[arg-type]
        )
        assert ku.context.languages == ["python"]

    def test_propose_bare_string_frameworks_coerced_to_list(self, client: Client):
        ku = client.propose(
            summary="Single fw",
            detail="Detail.",
            action="Action.",
            domains=["api"],
            frameworks="django",  # type: ignore[arg-type]
        )
        assert ku.context.frameworks == ["django"]

    def test_query_languages_boosts_ranking(self, client: Client):
        client.propose(
            summary="Python insight",
            detail="Detail.",
            action="Action.",
            domains=["api"],
            languages=["python"],
        )
        client.propose(
            summary="Go insight",
            detail="Detail.",
            action="Action.",
            domains=["api"],
            languages=["go"],
        )
        result = client.query(["api"], languages=["python"])
        assert len(result.units) == 2
        assert result.units[0].context.languages == ["python"]

    def test_query_pattern_forwarded_to_store(self, client: Client):
        """Client.query should pass `pattern` into the local store call so matching units rank first."""
        client.propose(
            summary="Pattern match",
            detail="Detail.",
            action="Action.",
            domains=["api"],
            pattern="api-client",
        )
        client.propose(
            summary="Pattern miss",
            detail="Detail.",
            action="Action.",
            domains=["api"],
        )
        result = client.query(["api"], pattern="api-client")
        assert len(result.units) == 2
        assert result.units[0].insight.summary == "Pattern match"


class TestFullLifecycle:
    def test_propose_confirm_query_flag(self, client: Client):
        ku = client.propose(
            summary="Stripe 402 means card_declined",
            detail="Check error.code, not error.type.",
            action="Handle card_declined explicitly.",
            domains=["api", "stripe"],
            languages=["python"],
        )

        result = client.query(["api", "stripe"], languages=["python"])
        assert len(result.units) == 1
        assert result.units[0].evidence.confidence == 0.5

        client.confirm(ku.id)
        result = client.query(["api", "stripe"])
        assert result.units[0].evidence.confidence == pytest.approx(0.6)

        client.flag(ku.id, FlagReason.STALE)
        result = client.query(["api", "stripe"])
        assert result.units[0].evidence.confidence == pytest.approx(0.45)
        assert len(result.units[0].flags) == 1


class TestRemoteConfig:
    def test_reads_addr_from_env(self, tmp_path: Path):
        with patch.dict("os.environ", {"CQ_ADDR": "http://localhost:8742"}):
            c = Client(local_db_path=tmp_path / "test.db")
            assert c.addr == "http://localhost:8742"
            c.close()

    def test_constructor_addr_takes_precedence(self, tmp_path: Path):
        with patch.dict("os.environ", {"CQ_ADDR": "http://env-addr"}):
            c = Client(
                addr="http://explicit-addr",
                local_db_path=tmp_path / "test.db",
            )
            assert c.addr == "http://explicit-addr"
            c.close()

    def test_reads_db_path_from_env(self, tmp_path: Path):
        db = tmp_path / "custom.db"
        with patch.dict("os.environ", {"CQ_LOCAL_DB_PATH": str(db)}):
            c = Client()
            assert c._store.db_path == db
            c.close()

    def test_default_timeout_used_when_not_specified(self, tmp_path: Path):
        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        assert c._http is not None
        assert c._http.timeout == httpx.Timeout(5.0)
        c.close()

    def test_custom_timeout_forwarded_to_http_client(self, tmp_path: Path):
        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db", timeout=15.0)
        assert c._http is not None
        assert c._http.timeout == httpx.Timeout(15.0)
        c.close()

    def test_timeout_without_remote_addr(self, tmp_path: Path):
        c = Client(local_db_path=tmp_path / "test.db", timeout=10.0)
        assert c._http is None
        c.close()


class TestRemoteIntegration:
    def test_remote_query_merges_with_local(self, tmp_path: Path, httpx_mock):
        """Remote results are merged with local results."""
        remote_unit = {
            "id": "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01",
            "domains": ["api"],
            "insight": {"summary": "S", "detail": "D", "action": "A"},
            "evidence": {
                "confidence": 0.8,
                "confirmations": 5,
                "first_observed": "2025-01-01T00:00:00Z",
                "last_confirmed": "2025-01-01T00:00:00Z",
            },
            "tier": "private",
        }
        httpx_mock.add_response(
            url=httpx.URL("http://test-remote/api/v1/knowledge", params={"domains": ["api"], "limit": "5"}),
            json={"data": [remote_unit]},
        )

        # Insert a local unit directly (propose with remote skips local store).
        local_client = Client(local_db_path=tmp_path / "test.db")
        local_client.propose(
            summary="Local insight",
            detail="D",
            action="A",
            domains=["api"],
        )
        local_client.close()

        c = Client(
            addr="http://test-remote",
            local_db_path=tmp_path / "test.db",
        )
        result = c.query(["api"])
        assert result.source == "remote"
        assert result.warnings == []
        assert len(result.units) == 2
        ids = {r.id for r in result.units}
        assert "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01" in ids
        c.close()

    def test_remote_query_sends_plural_language_and_framework_params(self, tmp_path: Path, httpx_mock):
        """Remote query sends plural 'languages'/'frameworks' keys, not singular."""
        remote_unit = {
            "id": "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01",
            "domains": ["api"],
            "insight": {"summary": "S", "detail": "D", "action": "A"},
            "tier": "private",
        }
        httpx_mock.add_response(
            url=httpx.URL(
                "http://test-remote/api/v1/knowledge",
                params={"domains": ["api"], "limit": "5", "languages": ["python"], "frameworks": ["django"]},
            ),
            json={"data": [remote_unit]},
        )

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        result = c.query(["api"], languages=["python"], frameworks=["django"])
        assert result.source == "remote"
        assert len(result.units) == 1
        assert result.units[0].id == "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01"
        c.close()

    def test_remote_query_includes_pattern_param_when_non_empty(self, tmp_path: Path, httpx_mock):
        """`_remote_query` should include `pattern` in the outgoing HTTP params when non-empty."""
        remote_unit = {
            "id": "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01",
            "domains": ["api"],
            "insight": {"summary": "S", "detail": "D", "action": "A"},
            "tier": "private",
        }
        httpx_mock.add_response(
            url=httpx.URL(
                "http://test-remote/api/v1/knowledge",
                params={"domains": ["api"], "limit": "5", "pattern": "api-client"},
            ),
            json={"data": [remote_unit]},
        )

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        result = c.query(["api"], pattern="api-client")
        assert result.source == "remote"
        assert len(result.units) == 1
        assert result.units[0].id == "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01"
        c.close()

    def test_remote_query_omits_pattern_param_when_empty(self, tmp_path: Path, httpx_mock):
        """`_remote_query` should omit `pattern` from outgoing params when empty."""
        remote_unit = {
            "id": "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01",
            "domains": ["api"],
            "insight": {"summary": "S", "detail": "D", "action": "A"},
            "tier": "private",
        }
        httpx_mock.add_response(
            url=httpx.URL("http://test-remote/api/v1/knowledge", params={"domains": ["api"], "limit": "5"}),
            json={"data": [remote_unit]},
        )

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        result = c.query(["api"])
        assert result.source == "remote"
        assert len(result.units) == 1
        c.close()

    def test_remote_query_warns_on_bare_array_response(self, tmp_path: Path, httpx_mock):
        """A server returning a bare JSON array (pre-envelope shape) must surface as a warning,
        not silently degrade to empty results."""
        httpx_mock.add_response(
            url=httpx.URL("http://test-remote/api/v1/knowledge", params={"domains": ["api"], "limit": "5"}),
            json=[{"id": "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa99"}],
        )

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        result = c.query(["api"])
        assert result.units == []
        assert any("envelope" in w or "data" in w for w in result.warnings)
        c.close()

    def test_remote_query_warns_on_missing_data_key(self, tmp_path: Path, httpx_mock):
        """A server returning a JSON object without a ``data`` key must surface as a warning."""
        httpx_mock.add_response(
            url=httpx.URL("http://test-remote/api/v1/knowledge", params={"domains": ["api"], "limit": "5"}),
            json={"results": []},
        )

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        result = c.query(["api"])
        assert result.units == []
        assert result.warnings, "missing data key should produce a warning"
        c.close()

    def test_propose_returns_server_response_when_remote_accepts(self, tmp_path: Path, httpx_mock):
        """When remote accepts, propose() returns the server-created unit."""
        server_unit = {
            "id": "ku_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbb01",
            "domains": ["api"],
            "insight": {"summary": "Remote only", "detail": "D", "action": "A"},
            "tier": "private",
        }
        httpx_mock.add_response(json={"knowledge_unit": server_unit}, status_code=200)

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        result = c.propose(summary="Remote only", detail="D", action="A", domains=["api"])

        assert result.id == "ku_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbb01"
        assert result.tier == Tier.PRIVATE
        assert c._store.all() == []
        c.close()

    def test_propose_falls_back_to_local_when_remote_unreachable(self, tmp_path: Path, httpx_mock):
        """When remote is unreachable, raise FallbackError with local_unit."""
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        c = Client(addr="http://unreachable", local_db_path=tmp_path / "test.db")
        with pytest.raises(FallbackError) as exc_info:
            c.propose(summary="Local fallback", detail="D", action="A", domains=["api"])

        fb = exc_info.value
        assert fb.local_unit.insight.summary == "Local fallback"
        assert isinstance(fb.__cause__, httpx.ConnectError)
        assert "Connection refused" in str(fb.__cause__)
        assert len(c._store.all()) == 1
        c.close()

    def test_propose_raises_when_remote_rejects(self, tmp_path: Path, httpx_mock):
        """When remote explicitly rejects, raise RemoteError and skip local."""
        httpx_mock.add_response(json={"detail": "bad request"}, status_code=400)

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        with pytest.raises(RemoteError):
            c.propose(summary="Rejected", detail="D", action="A", domains=["api"])

        assert c._store.all() == []
        c.close()

    def test_fallback_error_message_and_cause(self, tmp_path: Path, httpx_mock):
        """FallbackError exposes local_unit and chains __cause__ to the underlying error."""
        httpx_mock.add_response(json={"detail": "Invalid API key"}, status_code=401)

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        with pytest.raises(FallbackError) as exc_info:
            c.propose(summary="Chain", detail="D", action="A", domains=["api"])

        fb = exc_info.value
        assert str(fb) == "Stored locally after remote failure"
        assert isinstance(fb.__cause__, RemoteError)
        assert fb.__cause__.status_code == 401
        c.close()

    @pytest.mark.parametrize("status_code", [401, 403])
    def test_propose_auth_reject_falls_back_to_local(self, tmp_path: Path, httpx_mock, status_code: int):
        """When remote returns 401 or 403, raise FallbackError with local_unit."""
        httpx_mock.add_response(json={"detail": "Invalid API key"}, status_code=status_code)

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        with pytest.raises(FallbackError) as exc_info:
            c.propose(summary="Auth fallback", detail="D", action="A", domains=["api"])

        fb = exc_info.value
        assert fb.local_unit.insight.summary == "Auth fallback"
        assert isinstance(fb.__cause__, RemoteError)
        assert fb.__cause__.status_code == status_code
        assert len(c._store.all()) == 1
        c.close()

    @pytest.mark.parametrize("status_code", [500, 502, 503])
    def test_propose_server_error_falls_back_to_local(self, tmp_path: Path, httpx_mock, status_code: int):
        """When remote returns 5xx, raise FallbackError and persist the unit locally."""
        httpx_mock.add_response(json={"detail": "Upstream failure"}, status_code=status_code)

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        with pytest.raises(FallbackError) as exc_info:
            c.propose(summary="Server fallback", detail="D", action="A", domains=["api"])

        fb = exc_info.value
        assert fb.local_unit.insight.summary == "Server fallback"
        assert isinstance(fb.__cause__, RemoteError)
        assert fb.__cause__.status_code == status_code
        assert len(c._store.all()) == 1
        c.close()

    def test_drain_deletes_local_units_after_push(self, tmp_path: Path, httpx_mock):
        """After drain pushes a unit to remote, it is deleted from local store."""
        # First, create a local-only client and propose a unit.
        c = Client(local_db_path=tmp_path / "test.db")
        c.propose(summary="To drain", detail="D", action="A", domains=["api"])
        assert len(c._store.all()) == 1
        c.close()

        # Now open with remote configured; mock accepts the push.
        httpx_mock.add_response(json={}, status_code=200)
        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        result = c.drain()

        assert result.pushed == 1
        assert result.warnings == []
        assert c._store.all() == []
        c.close()

    def test_drain_keeps_local_unit_on_push_failure(self, tmp_path: Path, httpx_mock):
        """If drain fails to push a unit, it remains in local store."""
        c = Client(local_db_path=tmp_path / "test.db")
        c.propose(summary="Stuck locally", detail="D", action="A", domains=["api"])
        c.close()

        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))
        c = Client(addr="http://unreachable", local_db_path=tmp_path / "test.db")
        result = c.drain()

        assert result.pushed == 0
        assert len(result.warnings) == 1
        assert "Failed to drain unit" in result.warnings[0]
        assert len(c._store.all()) == 1
        c.close()

    def test_remote_failure_falls_back_to_local(self, tmp_path: Path, httpx_mock):
        """When remote API is unreachable, propose raises FallbackError; query still works."""
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        c = Client(
            addr="http://unreachable",
            local_db_path=tmp_path / "test.db",
        )
        with pytest.raises(FallbackError):
            c.propose(
                summary="Local only",
                detail="D",
                action="A",
                domains=["api"],
            )

        result = c.query(["api"])
        assert result.source == "local"
        assert len(result.warnings) == 1
        assert "Remote query failed" in result.warnings[0]
        assert len(result.units) == 1
        c.close()

    def test_confirm_routes_to_remote_for_non_local_tier(self, tmp_path: Path, httpx_mock):
        """confirm() routes to remote API when tier is non-local."""
        confirmed_unit = {
            "id": "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01",
            "domains": ["api"],
            "insight": {"summary": "S", "detail": "D", "action": "A"},
            "evidence": {"confidence": 0.6, "confirmations": 2},
            "tier": "private",
        }
        httpx_mock.add_response(
            url="http://test-remote/api/v1/knowledge/ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01/confirmations",
            json={"knowledge_unit": confirmed_unit},
            status_code=201,
        )

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        result = c.confirm("ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01", tier=Tier.PRIVATE)
        assert result.id == "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01"
        assert result.evidence.confidence == pytest.approx(0.6)
        assert result.tier == Tier.PRIVATE
        c.close()

    def test_flag_routes_to_remote_for_non_local_tier(self, tmp_path: Path, httpx_mock):
        """flag() routes to remote API when tier is non-local."""
        flagged_unit = {
            "id": "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01",
            "domains": ["api"],
            "insight": {"summary": "S", "detail": "D", "action": "A"},
            "evidence": {"confidence": 0.35},
            "flags": [{"reason": "stale"}],
            "tier": "private",
        }
        httpx_mock.add_response(
            url="http://test-remote/api/v1/knowledge/ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01/flags",
            json={"knowledge_unit": flagged_unit},
            status_code=201,
        )

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        result = c.flag("ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01", FlagReason.STALE, tier=Tier.PRIVATE)
        assert result.id == "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01"
        assert result.evidence.confidence == pytest.approx(0.35)
        assert len(result.flags) == 1
        c.close()

    def test_confirm_raises_remote_error_for_rejected_non_local(self, tmp_path: Path, httpx_mock):
        """confirm() raises RemoteError when remote rejects a non-local unit."""
        httpx_mock.add_response(json={"detail": "not found"}, status_code=404)

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        with pytest.raises(RemoteError):
            c.confirm("ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01", tier=Tier.PRIVATE)
        c.close()

    def test_flag_raises_remote_error_for_rejected_non_local(self, tmp_path: Path, httpx_mock):
        """flag() raises RemoteError when remote rejects a non-local unit."""
        httpx_mock.add_response(json={"detail": "not found"}, status_code=404)

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        with pytest.raises(RemoteError):
            c.flag("ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01", FlagReason.STALE, tier=Tier.PRIVATE)
        c.close()

    def test_confirm_raises_key_error_when_remote_unreachable_for_non_local(self, tmp_path: Path, httpx_mock):
        """confirm() raises KeyError when remote is unreachable for non-local unit."""
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        c = Client(addr="http://unreachable", local_db_path=tmp_path / "test.db")
        with pytest.raises(KeyError, match="Remote unreachable"):
            c.confirm("ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01", tier=Tier.PRIVATE)
        c.close()

    def test_flag_raises_key_error_when_remote_unreachable_for_non_local(self, tmp_path: Path, httpx_mock):
        """flag() raises KeyError when remote is unreachable for non-local unit."""
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        c = Client(addr="http://unreachable", local_db_path=tmp_path / "test.db")
        with pytest.raises(KeyError, match="Remote unreachable"):
            c.flag("ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01", FlagReason.STALE, tier=Tier.PRIVATE)
        c.close()

    def test_confirm_local_ignores_remote_rejection(self, tmp_path: Path, httpx_mock):
        """confirm() succeeds locally even when remote rejects."""
        from cq.models import Insight, create_knowledge_unit

        httpx_mock.add_response(json={"detail": "rejected"}, status_code=400)

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        unit = create_knowledge_unit(domains=["api"], insight=Insight(summary="S", detail="D", action="A"))
        c._store.insert(unit)

        confirmed = c.confirm(unit.id)
        assert confirmed.evidence.confidence == pytest.approx(0.6)
        c.close()

    def test_status_merges_remote_tier_counts(self, tmp_path: Path, httpx_mock):
        """status() merges local and remote tier counts."""
        httpx_mock.add_response(
            url=httpx.URL("http://test-remote/api/v1/knowledge/stats"),
            json={"total_count": 3, "tier_counts": {"private": 3, "public": 0}, "domain_counts": {}},
        )

        local_client = Client(local_db_path=tmp_path / "test.db")
        local_client.propose(summary="S", detail="D", action="A", domains=["api"])
        local_client.close()

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        stats = c.status()
        assert stats.tier_counts[Tier.LOCAL] == 1
        assert stats.tier_counts[Tier.PRIVATE] == 3
        assert stats.tier_counts[Tier.PUBLIC] == 0
        assert stats.total_count == 4
        c.close()

    def test_status_merges_remote_domain_counts(self, tmp_path: Path, httpx_mock):
        """status() merges remote domain counts into local domain counts, accumulating overlaps."""
        httpx_mock.add_response(
            url=httpx.URL("http://test-remote/api/v1/knowledge/stats"),
            json={
                "total_count": 5,
                "tier_counts": {"private": 5, "public": 0},
                "domain_counts": {"api": 3, "db": 2},
            },
        )

        # Local unit contributes to the "api" domain so we can verify accumulation.
        local_client = Client(local_db_path=tmp_path / "test.db")
        local_client.propose(summary="S", detail="D", action="A", domains=["api"])
        local_client.close()

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        stats = c.status()
        # "api" appears locally (1) and remotely (3) — counts must accumulate.
        assert stats.domain_counts["api"] == 4
        # "db" only appears on the remote.
        assert stats.domain_counts["db"] == 2
        c.close()

    def test_status_remote_unreachable_surfaces_warning(self, tmp_path: Path, httpx_mock, caplog):
        """A remote stats failure surfaces a warning + log, not a silent local-only result
        indistinguishable from a genuinely empty store."""
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        local_client = Client(local_db_path=tmp_path / "test.db")
        local_client.propose(summary="S", detail="D", action="A", domains=["api"])
        local_client.close()

        c = Client(addr="http://unreachable", local_db_path=tmp_path / "test.db")
        with caplog.at_level(logging.WARNING, logger="cq.client"):
            stats = c.status()
        assert stats.total_count == 1
        assert stats.tier_counts == {Tier.LOCAL: 1}
        assert stats.warnings, "remote failure should surface as a warning"
        assert any("unavailable" in w.lower() for w in stats.warnings)
        assert any("Remote stats unavailable" in r.message for r in caplog.records)
        c.close()

    def test_status_remote_http_error_surfaces_warning(self, tmp_path: Path, httpx_mock):
        """A remote stats HTTP error (e.g. 401 from a misconfigured key) surfaces as a warning
        rather than a silent local-only result."""
        httpx_mock.add_response(
            url=httpx.URL("http://test-remote/api/v1/knowledge/stats"),
            json={"detail": "Invalid API key"},
            status_code=401,
        )

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        stats = c.status()
        assert stats.tier_counts == {Tier.LOCAL: 0}
        assert stats.warnings, "remote HTTP error should surface as a warning"
        assert any("unavailable" in w.lower() for w in stats.warnings)
        c.close()

    def test_status_remote_non_object_body_surfaces_warning(self, tmp_path: Path, httpx_mock):
        """A 2xx stats body that is valid JSON but not an object (e.g. a bare array)
        must surface as a warning, not raise AttributeError from status()."""
        httpx_mock.add_response(
            url=httpx.URL("http://test-remote/api/v1/knowledge/stats"),
            json=[1, 2, 3],
        )

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        stats = c.status()
        assert stats.tier_counts == {Tier.LOCAL: 0}
        assert stats.warnings, "non-object stats body should surface as a warning"
        c.close()

    def test_status_ignores_local_tier_from_remote(self, tmp_path: Path, httpx_mock):
        """status() ignores 'local' tier in remote response to prevent double-counting."""
        httpx_mock.add_response(
            url=httpx.URL("http://test-remote/api/v1/knowledge/stats"),
            json={"total_count": 6, "tier_counts": {"local": 1, "private": 4, "public": 1}, "domain_counts": {}},
        )

        local_client = Client(local_db_path=tmp_path / "test.db")
        local_client.propose(summary="S", detail="D", action="A", domains=["api"])
        local_client.close()

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        stats = c.status()
        assert stats.tier_counts[Tier.LOCAL] == 1
        assert stats.tier_counts[Tier.PRIVATE] == 4
        assert stats.tier_counts[Tier.PUBLIC] == 1
        assert stats.total_count == 6
        c.close()

    def test_status_skips_and_logs_unknown_remote_tier(
        self, tmp_path: Path, httpx_mock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A remote tier this SDK's enum does not know is skipped, logged, and
        surfaced as a warning; not carried as a bare-string key nor summed into
        the total."""
        httpx_mock.add_response(
            url=httpx.URL("http://test-remote/api/v1/knowledge/stats"),
            json={"total_count": 13, "tier_counts": {"private": 4, "team": 9}, "domain_counts": {}},
        )

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        with caplog.at_level(logging.WARNING, logger="cq.client"):
            stats = c.status()
        assert stats.tier_counts == {Tier.LOCAL: 0, Tier.PRIVATE: 4}
        assert all(isinstance(key, Tier) for key in stats.tier_counts)
        assert stats.total_count == 4  # local 0 + private 4; unknown 'team' dropped
        assert any("team" in record.message for record in caplog.records)
        assert any("team" in warning for warning in stats.warnings)
        c.close()

    def test_status_decodes_store_stats_wire_shape(self, tmp_path: Path, httpx_mock) -> None:
        """status() decodes a remote body marshalled from the public StoreStats model.

        Pins the wire contract to the StoreStats vocabulary so the remote
        decoder and the public stats type cannot drift apart.
        """
        remote = StoreStats(
            total_count=7,
            domain_counts={"api": 4, "ci": 3},
            tier_counts={"private": 6, "public": 1},
        )
        httpx_mock.add_response(
            url=httpx.URL("http://test-remote/api/v1/knowledge/stats"),
            json=remote.model_dump(mode="json"),
        )

        local_client = Client(local_db_path=tmp_path / "test.db")
        local_client.propose(summary="S", detail="D", action="A", domains=["api"])
        local_client.close()

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        stats = c.status()
        assert stats.tier_counts == {Tier.LOCAL: 1, Tier.PRIVATE: 6, Tier.PUBLIC: 1}
        assert stats.total_count == 8
        # "api" appears locally (1) and remotely (4); counts must accumulate.
        assert stats.domain_counts["api"] == 5
        assert stats.domain_counts["ci"] == 3
        c.close()

    def test_flag_local_ignores_remote_rejection(self, tmp_path: Path, httpx_mock):
        """flag() succeeds locally even when remote rejects."""
        from cq.models import Insight, create_knowledge_unit

        httpx_mock.add_response(json={"detail": "rejected"}, status_code=400)

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        unit = create_knowledge_unit(domains=["api"], insight=Insight(summary="S", detail="D", action="A"))
        c._store.insert(unit)

        flagged = c.flag(unit.id, FlagReason.STALE)
        assert flagged.evidence.confidence == pytest.approx(0.35)
        c.close()


class TestClientApiBaseUrl:
    def test_remote_calls_use_resolved_api_base_url(self, tmp_path: Path):
        """`_remote_*` calls should be routed through the Resolver's api_base_url, not addr + /api/v1."""
        from cq.discovery import SUPPORTED_DISCOVERY_VERSION, NodeInfo

        class _StaticResolver:
            def resolve(self, addr: str) -> NodeInfo:
                return NodeInfo(
                    version=SUPPORTED_DISCOVERY_VERSION,
                    api_base_url="https://api.example.com/v2",
                    api_version="v1",
                )

            def close(self) -> None:
                """No-op; the test double owns no resources."""

        captured: list[httpx.URL] = []

        def capturing_send(self, request, **kwargs):
            captured.append(request.url)
            return httpx.Response(
                status_code=200,
                json={"total_count": 0, "tier_counts": {}, "domain_counts": {}},
                request=request,
            )

        with patch.object(httpx.Client, "send", capturing_send):
            c = Client(
                addr="https://node.example.com",
                local_db_path=tmp_path / "test.db",
                _resolver=_StaticResolver(),  # type: ignore[arg-type]
            )
            c.status()
            c.close()

        assert len(captured) == 1
        assert str(captured[0]) == "https://api.example.com/v2/knowledge/stats"

    def test_trailing_slash_in_api_base_url_is_normalized(self, tmp_path: Path):
        """A trailing slash in the resolved api_base_url must not produce // in the request URL."""
        from cq.discovery import SUPPORTED_DISCOVERY_VERSION, NodeInfo

        class _TrailingSlashResolver:
            def resolve(self, addr: str) -> NodeInfo:
                return NodeInfo(
                    version=SUPPORTED_DISCOVERY_VERSION,
                    api_base_url="https://api.example.com/v2/",
                    api_version="v1",
                )

            def close(self) -> None:
                """No-op; the test double owns no resources."""

        captured: list[httpx.URL] = []

        def capturing_send(self, request, **kwargs):
            captured.append(request.url)
            return httpx.Response(
                status_code=200,
                json={"total_count": 0, "tier_counts": {}, "domain_counts": {}},
                request=request,
            )

        with patch.object(httpx.Client, "send", capturing_send):
            c = Client(
                addr="https://node.example.com",
                local_db_path=tmp_path / "test.db",
                _resolver=_TrailingSlashResolver(),  # type: ignore[arg-type]
            )
            c.status()
            c.close()

        assert len(captured) == 1
        assert str(captured[0]) == "https://api.example.com/v2/knowledge/stats"


class TestClientDiscoveryErrorPropagation:
    """DiscoveryError from the Resolver surfaces terminally to the caller.

    The Client's fallback paths catch httpx.HTTPError and RemoteError (for
    transport and server-side faults), but DiscoveryError signals operator
    or client misconfiguration that local-storage fallback cannot repair.
    These tests pin that contract for every public method that touches the
    remote.
    """

    class _RaisingResolver:
        def resolve(self, addr: str):
            from cq.discovery import DiscoveryError

            raise DiscoveryError("test discovery failure")

        def close(self) -> None:
            """No-op; the test double owns no resources."""

    def test_query_propagates_discovery_error(self, tmp_path: Path):
        from cq.discovery import DiscoveryError

        c = Client(
            addr="https://node.example.com",
            local_db_path=tmp_path / "test.db",
            _resolver=self._RaisingResolver(),  # type: ignore[arg-type]
        )
        with pytest.raises(DiscoveryError):
            c.query(["python"])
        c.close()

    def test_propose_propagates_discovery_error(self, tmp_path: Path):
        from cq.discovery import DiscoveryError

        c = Client(
            addr="https://node.example.com",
            local_db_path=tmp_path / "test.db",
            _resolver=self._RaisingResolver(),  # type: ignore[arg-type]
        )
        with pytest.raises(DiscoveryError):
            c.propose(
                summary="Use connection pooling",
                detail="Connections are expensive.",
                action="Pool them.",
                domains=["python"],
            )
        c.close()

    def test_confirm_propagates_discovery_error(self, tmp_path: Path):
        from cq.discovery import DiscoveryError

        c = Client(
            addr="https://node.example.com",
            local_db_path=tmp_path / "test.db",
            _resolver=self._RaisingResolver(),  # type: ignore[arg-type]
        )
        with pytest.raises(DiscoveryError):
            c.confirm("nonexistent-id", tier=Tier.PRIVATE)
        c.close()

    def test_flag_propagates_discovery_error(self, tmp_path: Path):
        from cq.discovery import DiscoveryError

        c = Client(
            addr="https://node.example.com",
            local_db_path=tmp_path / "test.db",
            _resolver=self._RaisingResolver(),  # type: ignore[arg-type]
        )
        with pytest.raises(DiscoveryError):
            c.flag("nonexistent-id", FlagReason.INCORRECT, tier=Tier.PRIVATE)
        c.close()

    def test_drain_propagates_discovery_error(self, tmp_path: Path):
        from cq.discovery import DiscoveryError

        c = Client(
            addr="https://node.example.com",
            local_db_path=tmp_path / "test.db",
            _resolver=self._RaisingResolver(),  # type: ignore[arg-type]
        )
        # Seed one local unit so drain has work to do; without it the
        # for-loop body never runs and the resolver is never invoked.
        from cq.models import Context, Insight, create_knowledge_unit

        unit = create_knowledge_unit(
            domains=["python"],
            insight=Insight(summary="s", detail="d", action="a"),
            context=Context(languages=[], frameworks=[], pattern=""),
            created_by="",
        )
        c._store.insert(unit)
        with pytest.raises(DiscoveryError):
            c.drain()
        c.close()

    def test_transport_failure_still_falls_back_on_propose(self, tmp_path: Path):
        """A resolver that succeeds combined with an HTTP transport failure should
        still produce the historical FallbackError so the local-store fallback
        path is unaffected by Resolver wiring.
        """
        from cq.discovery import SUPPORTED_DISCOVERY_VERSION, NodeInfo

        class _StaticResolver:
            def resolve(self, addr: str) -> NodeInfo:
                return NodeInfo(
                    version=SUPPORTED_DISCOVERY_VERSION,
                    api_base_url="https://api.example.com/v1",
                    api_version="v1",
                )

            def close(self) -> None:
                """No-op; the test double owns no resources."""

        def transport_failing_send(self, request, **kwargs):
            raise httpx.ConnectError("simulated network failure")

        with patch.object(httpx.Client, "send", transport_failing_send):
            c = Client(
                addr="https://node.example.com",
                local_db_path=tmp_path / "test.db",
                _resolver=_StaticResolver(),  # type: ignore[arg-type]
            )
            with pytest.raises(FallbackError):
                c.propose(
                    summary="Use connection pooling",
                    detail="Connections are expensive.",
                    action="Pool them.",
                    domains=["python"],
                )
            c.close()


class TestRealResolver404Fallback:
    """Pin the 404-fallback URL contract end-to-end through a real Resolver.

    When the node does not publish a discovery document, the Resolver synthesizes
    `addr + DEFAULT_API_PATH` and the Client routes subsequent API calls there.
    This test exercises the real Resolver (no `_resolver=` injection) so the
    `/api/v1/<resource>` contract stays pinned against future drift in either
    the Resolver or the Client.
    """

    def test_well_known_404_routes_api_calls_to_default_api_path(self, tmp_path: Path):
        captured: list[httpx.URL] = []

        def capturing_send(self, request, **kwargs):
            captured.append(request.url)
            if request.url.path == "/.well-known/cq-node.json":
                return httpx.Response(status_code=404, request=request)
            if request.url.path == "/api/v1/knowledge":
                return httpx.Response(
                    status_code=200,
                    json={"data": []},
                    request=request,
                )
            raise AssertionError(f"unexpected request {request.url}")

        with patch.object(httpx.Client, "send", capturing_send):
            c = Client(
                addr="https://node.example.com",
                local_db_path=tmp_path / "test.db",
            )
            c.query(["api"], limit=1)
            c.close()

        assert len(captured) == 2
        assert captured[0].path == "/.well-known/cq-node.json"
        assert captured[0].host == "node.example.com"
        assert captured[1].path == "/api/v1/knowledge"
        assert captured[1].host == "node.example.com"


class TestStaticResolverFixture:
    """Smoke tests that exercise the shared ``static_resolver`` conftest fixture.

    The fixture synthesizes the same ``addr + /api/v1`` suffix the default
    discovery fallback produces, so assertions against ``/api/v1/...`` paths
    hold for clients wired through the fixture without an HTTP probe.
    """

    def test_query_routes_through_static_resolver(self, tmp_path: Path, httpx_mock, static_resolver):
        remote_unit = {
            "id": "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01",
            "domains": ["api"],
            "insight": {"summary": "S", "detail": "D", "action": "A"},
            "tier": "private",
        }
        httpx_mock.add_response(
            url=httpx.URL("http://test-remote/api/v1/knowledge", params={"domains": ["api"], "limit": "5"}),
            json={"data": [remote_unit]},
        )

        c = Client(
            addr="http://test-remote",
            local_db_path=tmp_path / "test.db",
            _resolver=static_resolver,
        )
        result = c.query(["api"])
        assert result.source == "remote"
        assert len(result.units) == 1
        assert result.units[0].id == "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01"
        c.close()

    def test_propose_routes_through_static_resolver(self, tmp_path: Path, httpx_mock, static_resolver):
        server_unit = {
            "id": "ku_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbb01",
            "domains": ["api"],
            "insight": {"summary": "Remote only", "detail": "D", "action": "A"},
            "tier": "private",
        }
        httpx_mock.add_response(
            url=httpx.URL("http://test-remote/api/v1/knowledge"),
            json={"knowledge_unit": server_unit},
            status_code=200,
        )

        c = Client(
            addr="http://test-remote",
            local_db_path=tmp_path / "test.db",
            _resolver=static_resolver,
        )
        result = c.propose(summary="Remote only", detail="D", action="A", domains=["api"])
        assert result.id == "ku_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbb01"
        c.close()


@pytest.fixture()
def httpx_mock():
    """Minimal httpx mock for testing remote API calls."""
    responses: list[dict] = []
    exceptions: list[Exception] = []

    class _Mock:
        def add_response(self, url=None, json=None, status_code=200):
            responses.append({"url": url, "json": json, "status_code": status_code})

        def add_exception(self, exc: Exception):
            exceptions.append(exc)

    mock = _Mock()

    def patched_send(self, request, **kwargs):
        # Treat the discovery probe as unconfigured so the resolver falls back
        # to its `addr + /api/v1` defaults; the queued responses in these tests
        # describe the API call under test, not the probe.
        if request.url.path.endswith("/.well-known/cq-node.json"):
            return httpx.Response(status_code=404, request=request)
        if exceptions:
            raise exceptions.pop(0)
        for idx, resp_config in enumerate(responses):
            expected_url = resp_config["url"]
            if expected_url is None or request.url == expected_url:
                responses.pop(idx)
                return httpx.Response(
                    status_code=resp_config["status_code"],
                    json=resp_config["json"],
                    request=request,
                )
        return httpx.Response(status_code=404, request=request)

    with patch.object(httpx.Client, "send", patched_send):
        yield mock
