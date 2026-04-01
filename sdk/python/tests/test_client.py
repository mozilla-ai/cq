"""Tests for Client."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from cq.client import Client, RemoteError
from cq.models import FlagReason, Tier


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[Client]:
    c = Client(local_db_path=tmp_path / "test.db")
    yield c
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

        results = client.query(["databases"])
        assert len(results) == 1
        assert results[0].id == ku.id

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
            assert c.query(["testing"])[0].id == ku.id

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
        results = client.query("api")  # type: ignore[arg-type]
        assert len(results) == 1

    def test_query_bare_string_languages_coerced_to_list(self, client: Client):
        client.propose(
            summary="Python insight",
            detail="Detail.",
            action="Action.",
            domains=["api"],
            languages=["python"],
        )
        results = client.query(["api"], languages="python")  # type: ignore[arg-type]
        assert len(results) == 1
        assert results[0].context.languages == ["python"]

    def test_query_bare_string_frameworks_coerced_to_list(self, client: Client):
        client.propose(
            summary="Django insight",
            detail="Detail.",
            action="Action.",
            domains=["web"],
            frameworks=["django"],
        )
        results = client.query(["web"], frameworks="django")  # type: ignore[arg-type]
        assert len(results) == 1
        assert results[0].context.frameworks == ["django"]

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
        results = client.query(["api"], languages=["python"])
        assert len(results) == 2
        assert results[0].context.languages == ["python"]


class TestFullLifecycle:
    def test_propose_confirm_query_flag(self, client: Client):
        ku = client.propose(
            summary="Stripe 402 means card_declined",
            detail="Check error.code, not error.type.",
            action="Handle card_declined explicitly.",
            domains=["api", "stripe"],
            languages=["python"],
        )

        results = client.query(["api", "stripe"], languages=["python"])
        assert len(results) == 1
        assert results[0].evidence.confidence == 0.5

        client.confirm(ku.id)
        results = client.query(["api", "stripe"])
        assert results[0].evidence.confidence == pytest.approx(0.6)

        client.flag(ku.id, FlagReason.STALE)
        results = client.query(["api", "stripe"])
        assert results[0].evidence.confidence == pytest.approx(0.45)
        assert len(results[0].flags) == 1


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
            url=httpx.URL("http://test-remote/query", params={"domains": ["api"], "limit": "5"}),
            json=[remote_unit],
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
        results = c.query(["api"])
        assert len(results) == 2
        ids = {r.id for r in results}
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
                "http://test-remote/query",
                params={"domains": ["api"], "limit": "5", "languages": ["python"], "frameworks": ["django"]},
            ),
            json=[remote_unit],
        )

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        results = c.query(["api"], languages=["python"], frameworks=["django"])
        assert len(results) == 1
        assert results[0].id == "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01"
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
        """When remote is unreachable, the unit is stored locally as fallback."""
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        c = Client(addr="http://unreachable", local_db_path=tmp_path / "test.db")
        c.propose(summary="Local fallback", detail="D", action="A", domains=["api"])

        units = c._store.all()
        assert len(units) == 1
        assert units[0].insight.summary == "Local fallback"
        c.close()

    def test_propose_raises_when_remote_rejects(self, tmp_path: Path, httpx_mock):
        """When remote explicitly rejects, raise RemoteError and skip local."""
        httpx_mock.add_response(json={"detail": "bad request"}, status_code=400)

        c = Client(addr="http://test-remote", local_db_path=tmp_path / "test.db")
        with pytest.raises(RemoteError):
            c.propose(summary="Rejected", detail="D", action="A", domains=["api"])

        assert c._store.all() == []
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
        pushed = c.drain()

        assert pushed == 1
        assert c._store.all() == []
        c.close()

    def test_drain_keeps_local_unit_on_push_failure(self, tmp_path: Path, httpx_mock):
        """If drain fails to push a unit, it remains in local store."""
        c = Client(local_db_path=tmp_path / "test.db")
        c.propose(summary="Stuck locally", detail="D", action="A", domains=["api"])
        c.close()

        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))
        c = Client(addr="http://unreachable", local_db_path=tmp_path / "test.db")
        pushed = c.drain()

        assert pushed == 0
        assert len(c._store.all()) == 1
        c.close()

    def test_remote_failure_falls_back_to_local(self, tmp_path: Path, httpx_mock):
        """When remote API is unreachable, local results still returned."""
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        c = Client(
            addr="http://unreachable",
            local_db_path=tmp_path / "test.db",
        )
        c.propose(
            summary="Local only",
            detail="D",
            action="A",
            domains=["api"],
        )

        results = c.query(["api"])
        assert len(results) == 1
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
            url="http://test-remote/confirm/ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01",
            json={"knowledge_unit": confirmed_unit},
            status_code=200,
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
            url="http://test-remote/flag/ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01",
            json={"knowledge_unit": flagged_unit},
            status_code=200,
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
