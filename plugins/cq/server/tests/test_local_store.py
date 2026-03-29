import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from cq_mcp.knowledge_unit import (
    Context,
    Evidence,
    FlagReason,
    Insight,
    KnowledgeUnit,
    Tier,
    create_knowledge_unit,
)
from cq_mcp.local_store import (
    _FTS_MAX_TERM_LENGTH,
    _FTS_MAX_TERMS,
    LocalStore,
    TeamSyncStatus,
    _build_fts_match_expr,
    _default_db_path,
    _migrate_legacy_db,
)
from cq_mcp.scoring import apply_confirmation, apply_flag


def _make_insight(**overrides: Any) -> Insight:
    defaults = {
        "summary": "Use connection pooling",
        "detail": "Database connections are expensive to create.",
        "action": "Configure a connection pool with a max size of 10.",
    }
    return Insight(**{**defaults, **overrides})


def _make_unit(**overrides: Any) -> KnowledgeUnit:
    defaults = {
        "domain": ["databases", "performance"],
        "insight": _make_insight(),
    }
    return create_knowledge_unit(**{**defaults, **overrides})


def _inspect_connection(db_path: Path) -> sqlite3.Connection:
    """Open a test inspection connection with foreign key enforcement enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _inspect_domains(db_path: Path, unit_id: str) -> list[str]:
    """Read domain tags directly from SQLite for test assertions."""
    conn = _inspect_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT domain FROM knowledge_unit_domains WHERE unit_id = ? ORDER BY domain",
            (unit_id,),
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def _inspect_tables(db_path: Path) -> list[str]:
    """List user tables in the SQLite database."""
    conn = _inspect_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def _inspect_sync_metadata(db_path: Path, unit_id: str) -> dict[str, str | None] | None:
    """Read team sync metadata directly from SQLite for test assertions."""
    conn = _inspect_connection(db_path)
    try:
        row = conn.execute(
            "SELECT team_sync_status, team_sync_attempted_at, team_sync_error "
            "FROM knowledge_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "status": row[0],
            "attempted_at": row[1],
            "error": row[2],
        }
    finally:
        conn.close()


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[LocalStore]:
    s = LocalStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


class TestBuildFtsMatchExpr:
    """Tests for the isolated FTS5 expression builder.

    This function is the sole boundary between untrusted input and the
    FTS5 MATCH query engine. Every term must be wrapped in double quotes
    and any embedded double quotes must be stripped, so no input can
    alter the structure of the expression.
    """

    def test_single_clean_term(self) -> None:
        assert _build_fts_match_expr(["databases"]) == '"databases"'

    def test_multiple_terms_joined_with_or(self) -> None:
        result = _build_fts_match_expr(["api", "payments"])
        assert result == '"api" OR "payments"'

    def test_hyphens_preserved(self) -> None:
        assert _build_fts_match_expr(["setup-uv"]) == '"setup-uv"'

    def test_slashes_preserved(self) -> None:
        assert _build_fts_match_expr(["path/to/file"]) == '"path/to/file"'

    def test_backslashes_preserved(self) -> None:
        assert _build_fts_match_expr(["back\\slash"]) == '"back\\slash"'

    def test_double_quotes_stripped(self) -> None:
        assert _build_fts_match_expr(['bad"term']) == '"badterm"'

    def test_only_quotes_yields_empty(self) -> None:
        assert _build_fts_match_expr(['"""']) == ""

    def test_interspersed_quotes_stripped(self) -> None:
        assert _build_fts_match_expr(['a"b"c']) == '"abc"'

    def test_whitespace_stripped(self) -> None:
        assert _build_fts_match_expr(["  spaced  "]) == '"spaced"'

    def test_quotes_and_whitespace_stripped(self) -> None:
        assert _build_fts_match_expr(['" spaced "']) == '"spaced"'

    def test_empty_list_yields_empty(self) -> None:
        assert _build_fts_match_expr([]) == ""

    def test_all_terms_empty_after_cleaning(self) -> None:
        assert _build_fts_match_expr(['""', '"', "  "]) == ""

    def test_mixed_clean_and_dirty_terms(self) -> None:
        result = _build_fts_match_expr(["api", '"""', "payments"])
        assert result == '"api" OR "payments"'

    def test_wildcards_preserved(self) -> None:
        assert _build_fts_match_expr(["term*"]) == '"term*"'

    def test_braces_preserved(self) -> None:
        assert _build_fts_match_expr(["{near}"]) == '"{near}"'

    def test_colons_preserved(self) -> None:
        assert _build_fts_match_expr(["col:filter"]) == '"col:filter"'

    @pytest.mark.parametrize(
        "malicious",
        [
            'term"OR"1"OR"',  # OR injection attempt.
            '") OR (id:',  # Column filter injection attempt.
            '" OR ""',  # Quote-escape injection attempt.
        ],
        ids=["or_injection", "column_filter", "quote_escape"],
    )
    def test_injection_attempts_produce_safe_output(self, malicious: str) -> None:
        result = _build_fts_match_expr([malicious])
        if not result:
            return
        # The output must have balanced quotes.
        assert result.count('"') % 2 == 0, "Unbalanced quotes in output"
        # The output must start and end with a double quote,
        # proving it is wrapped in a phrase delimiter.
        assert result[0] == '"', f"Output does not start with quote: {result}"
        assert result[-1] == '"', f"Output does not end with quote: {result}"

    @pytest.mark.parametrize(
        ("malicious", "expected"),
        [
            ('term"OR"1"OR"', '"termOR1OR"'),
            ('") OR (id:', '") OR (id:"'),
            ('" OR ""', '"OR"'),
        ],
        ids=["or_injection", "column_filter", "quote_escape"],
    )
    def test_injection_attempts_exact_output(self, malicious: str, expected: str) -> None:
        """Pin the exact output for injection attempts to catch regressions."""
        assert _build_fts_match_expr([malicious]) == expected

    def test_truncates_excess_terms(self) -> None:
        terms = [f"term{i}" for i in range(_FTS_MAX_TERMS + 10)]
        result = _build_fts_match_expr(terms)
        assert result.count(" OR ") == _FTS_MAX_TERMS - 1

    def test_truncates_long_terms(self) -> None:
        long_term = "a" * (_FTS_MAX_TERM_LENGTH + 50)
        result = _build_fts_match_expr([long_term])
        # Quoted term plus two quotes.
        assert len(result) == _FTS_MAX_TERM_LENGTH + 2


class TestAutoCreateSchema:
    def test_creates_database_file(self, tmp_path: Path):
        db_path = tmp_path / "subdir" / "nested" / "test.db"
        store = LocalStore(db_path=db_path)
        store.close()
        assert db_path.exists()

    def test_creates_knowledge_units_table(self, store: LocalStore):
        tables = _inspect_tables(store.db_path)
        assert "knowledge_units" in tables

    def test_creates_domains_table(self, store: LocalStore):
        tables = _inspect_tables(store.db_path)
        assert "knowledge_unit_domains" in tables

    def test_creates_team_sync_columns(self, store: LocalStore):
        unit = _make_unit(domain=["api"])
        store.insert(unit)
        metadata = _inspect_sync_metadata(store.db_path, unit.id)
        assert metadata == {
            "status": TeamSyncStatus.NOT_APPLICABLE.value,
            "attempted_at": None,
            "error": None,
        }

    def test_idempotent_schema_creation(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        store1 = LocalStore(db_path=db_path)
        store1.close()
        store2 = LocalStore(db_path=db_path)
        store2.close()


class TestContextManager:
    def test_usable_as_context_manager(self, tmp_path: Path):
        with LocalStore(db_path=tmp_path / "test.db") as store:
            unit = _make_unit()
            store.insert(unit)
            assert store.get(unit.id) == unit

    def test_close_is_idempotent(self, tmp_path: Path):
        store = LocalStore(db_path=tmp_path / "test.db")
        store.close()
        store.close()

    def test_operations_after_close_raise(self, tmp_path: Path):
        store = LocalStore(db_path=tmp_path / "test.db")
        store.close()
        with pytest.raises(RuntimeError, match="LocalStore is closed"):
            store.insert(_make_unit())
        with pytest.raises(RuntimeError, match="LocalStore is closed"):
            store.get("ku_any")
        with pytest.raises(RuntimeError, match="LocalStore is closed"):
            store.update(_make_unit())
        with pytest.raises(RuntimeError, match="LocalStore is closed"):
            store.query(["databases"])


class TestInsert:
    def test_insert_and_retrieve(self, store: LocalStore):
        unit = _make_unit()
        store.insert(unit)
        retrieved = store.get(unit.id)
        assert retrieved == unit

    def test_insert_duplicate_raises(self, store: LocalStore):
        unit = _make_unit()
        store.insert(unit)
        with pytest.raises(sqlite3.IntegrityError):
            store.insert(unit)

    def test_insert_stores_domain_tags(self, store: LocalStore):
        unit = _make_unit(domain=["api", "payments", "stripe"])
        store.insert(unit)
        domains = _inspect_domains(store.db_path, unit.id)
        assert domains == ["api", "payments", "stripe"]

    def test_insert_with_empty_domains_raises(self, store: LocalStore):
        unit = _make_unit(domain=["  ", ""])
        with pytest.raises(ValueError, match="At least one non-empty domain"):
            store.insert(unit)

    def test_insert_persists_team_sync_metadata(self, store: LocalStore):
        unit = _make_unit(domain=["api"])
        store.insert(
            unit,
            team_sync_status=TeamSyncStatus.PENDING,
            team_sync_error="Team API unreachable during propose.",
        )
        metadata = _inspect_sync_metadata(store.db_path, unit.id)
        assert metadata is not None
        assert metadata["status"] == TeamSyncStatus.PENDING.value
        assert metadata["attempted_at"] is None
        assert metadata["error"] == "Team API unreachable during propose."


class TestGet:
    def test_returns_none_for_missing_id(self, store: LocalStore):
        assert store.get("ku_nonexistent") is None

    def test_roundtrip_preserves_all_fields(self, store: LocalStore):
        unit = _make_unit(
            domain=["api"],
            context=Context(languages=["python"], frameworks=["django"], pattern="web-api"),
            tier=Tier.LOCAL,
            created_by="agent:test-machine",
        )
        store.insert(unit)
        retrieved = store.get(unit.id)
        assert retrieved is not None
        assert retrieved.domain == unit.domain
        assert retrieved.context == unit.context
        assert retrieved.tier == unit.tier
        assert retrieved.created_by == unit.created_by
        assert retrieved.evidence == unit.evidence
        assert retrieved.insight == unit.insight

    def test_team_sync_status_returns_none_for_missing_id(self, store: LocalStore):
        assert store.team_sync_status("ku_nonexistent") is None


class TestUpdate:
    def test_update_persists_changes(self, store: LocalStore):
        unit = _make_unit()
        store.insert(unit)

        confirmed = apply_confirmation(unit)
        store.update(confirmed)

        retrieved = store.get(unit.id)
        assert retrieved is not None
        assert retrieved.evidence.confirmations == 2
        assert retrieved.evidence.confidence == pytest.approx(0.6)

    def test_update_missing_unit_raises(self, store: LocalStore):
        unit = _make_unit()
        with pytest.raises(KeyError, match="Knowledge unit not found"):
            store.update(unit)

    def test_update_with_empty_domains_raises(self, store: LocalStore):
        unit = _make_unit(domain=["databases"])
        store.insert(unit)
        updated = unit.model_copy(update={"domain": ["  ", ""]})
        with pytest.raises(ValueError, match="At least one non-empty domain"):
            store.update(updated)

    def test_update_refreshes_domain_tags(self, store: LocalStore):
        unit = _make_unit(domain=["databases"])
        store.insert(unit)

        updated = unit.model_copy(update={"domain": ["databases", "caching"]})
        store.update(updated)

        retrieved = store.get(unit.id)
        assert retrieved is not None
        assert set(retrieved.domain) == {"databases", "caching"}

    def test_update_after_flag_reduces_confidence(self, store: LocalStore):
        unit = _make_unit()
        store.insert(unit)

        flagged = apply_flag(unit, FlagReason.STALE)
        store.update(flagged)

        retrieved = store.get(unit.id)
        assert retrieved is not None
        assert retrieved.evidence.confidence == pytest.approx(0.35)
        assert len(retrieved.flags) == 1

    def test_update_team_sync_status_persists_metadata(self, store: LocalStore):
        unit = _make_unit(domain=["api"])
        store.insert(unit, team_sync_status=TeamSyncStatus.PENDING)

        store.update_team_sync_status(
            unit.id,
            TeamSyncStatus.SYNCED,
            attempted_at=datetime.now(UTC),
        )

        metadata = store.team_sync_status(unit.id)
        assert metadata is not None
        assert metadata["status"] == TeamSyncStatus.SYNCED.value
        assert metadata["attempted_at"] is not None
        assert metadata["error"] is None

    def test_update_team_sync_status_missing_unit_raises(self, store: LocalStore):
        with pytest.raises(KeyError, match="Knowledge unit not found"):
            store.update_team_sync_status("ku_missing", TeamSyncStatus.PENDING)


class TestQuery:
    def test_returns_units_with_matching_domain(self, store: LocalStore):
        unit = _make_unit(domain=["databases", "performance"])
        store.insert(unit)

        results = store.query(["databases"])
        assert len(results) == 1
        assert results[0].id == unit.id

    def test_returns_empty_for_no_match(self, store: LocalStore):
        unit = _make_unit(domain=["databases"])
        store.insert(unit)

        results = store.query(["networking"])
        assert results == []

    def test_returns_empty_for_empty_domains(self, store: LocalStore):
        unit = _make_unit(domain=["databases"])
        store.insert(unit)

        results = store.query([])
        assert results == []

    def test_rejects_non_positive_limit(self, store: LocalStore):
        with pytest.raises(ValueError, match="limit must be positive"):
            store.query(["databases"], limit=0)
        with pytest.raises(ValueError, match="limit must be positive"):
            store.query(["databases"], limit=-1)

    def test_ranks_by_domain_overlap(self, store: LocalStore):
        high_relevance = _make_unit(domain=["databases", "performance"])
        low_relevance = _make_unit(domain=["databases", "networking"])
        store.insert(high_relevance)
        store.insert(low_relevance)

        results = store.query(["databases", "performance"])
        assert len(results) == 2
        assert results[0].id == high_relevance.id

    def test_respects_limit(self, store: LocalStore):
        for _ in range(10):
            store.insert(_make_unit(domain=["databases"]))

        results = store.query(["databases"], limit=3)
        assert len(results) == 3

    def test_language_boosts_ranking_without_excluding(self, store: LocalStore):
        python_unit = _make_unit(
            domain=["databases"],
            context=Context(languages=["python"]),
        )
        go_unit = _make_unit(
            domain=["databases"],
            context=Context(languages=["go"]),
        )
        store.insert(python_unit)
        store.insert(go_unit)

        results = store.query(["databases"], language="python")
        assert len(results) == 2
        assert results[0].id == python_unit.id

    def test_framework_boosts_ranking_without_excluding(self, store: LocalStore):
        django_unit = _make_unit(
            domain=["web"],
            context=Context(frameworks=["django"]),
        )
        flask_unit = _make_unit(
            domain=["web"],
            context=Context(frameworks=["flask"]),
        )
        store.insert(django_unit)
        store.insert(flask_unit)

        results = store.query(["web"], framework="django")
        assert len(results) == 2
        assert results[0].id == django_unit.id

    def test_combined_language_and_framework_boosts_ranking(self, store: LocalStore):
        match = _make_unit(
            domain=["web"],
            context=Context(languages=["python"], frameworks=["django"]),
        )
        partial = _make_unit(
            domain=["web"],
            context=Context(languages=["python"], frameworks=["flask"]),
        )
        store.insert(match)
        store.insert(partial)

        results = store.query(["web"], language="python", framework="django")
        assert len(results) == 2
        assert results[0].id == match.id

    def test_higher_confidence_ranks_higher(self, store: LocalStore):
        low_conf = _make_unit(domain=["databases"])
        high_conf = _make_unit(domain=["databases"])

        store.insert(low_conf)
        store.insert(high_conf)

        confirmed = apply_confirmation(high_conf)
        confirmed = apply_confirmation(confirmed)
        store.update(confirmed)

        results = store.query(["databases"])
        assert results[0].id == high_conf.id


class TestFTS:
    def test_fts_finds_units_by_summary_text(self, store: LocalStore):
        unit = _make_unit(
            domain=["ci"],
            insight=Insight(
                summary="actions/checkout latest version is v6",
                detail="LLMs default to v4.",
                action="Pin to v6.",
            ),
        )
        store.insert(unit)

        results = store.query(["checkout"])
        assert len(results) == 1
        assert results[0].id == unit.id

    def test_fts_finds_units_by_detail_text(self, store: LocalStore):
        unit = _make_unit(
            domain=["ci"],
            insight=Insight(
                summary="Stale action versions",
                detail="The astral-sh/setup-uv action is now at v7.",
                action="Update to v7.",
            ),
        )
        store.insert(unit)

        results = store.query(["setup-uv"])
        assert len(results) == 1
        assert results[0].id == unit.id

    def test_fts_deduplicates_with_domain_matches(self, store: LocalStore):
        unit = _make_unit(
            domain=["github-actions"],
            insight=Insight(
                summary="github-actions checkout is at v6",
                detail="Detail.",
                action="Action.",
            ),
        )
        store.insert(unit)

        results = store.query(["github-actions"])
        assert len(results) == 1

    def test_fts_query_with_double_quote_in_domain(self, store: LocalStore):
        """A double quote in a query domain must not poison the FTS path.

        When one query term contains a double quote, the entire FTS MATCH
        expression becomes malformed. Units only discoverable via FTS text
        search (not domain-tag match) are silently lost.
        """
        unit = _make_unit(
            domain=["ci"],
            insight=Insight(
                summary="The stripe-mock server requires Docker",
                detail="Run stripe-mock in Docker for integration tests.",
                action="Use docker compose.",
            ),
        )
        store.insert(unit)

        # Baseline: FTS finds "stripe-mock" via summary text.
        results = store.query(["stripe-mock"])
        assert len(results) == 1
        assert results[0].id == unit.id

        # A term with a double quote must not poison the FTS MATCH.
        results = store.query(["stripe-mock", 'bad"term'])
        assert len(results) == 1
        assert results[0].id == unit.id

    def test_fts_query_with_only_double_quote_domain(self, store: LocalStore):
        """A domain that is only a double quote should not crash FTS."""
        unit = _make_unit(
            domain=["ci"],
            insight=Insight(
                summary="The stripe-mock server requires Docker",
                detail="Run stripe-mock in Docker for integration tests.",
                action="Use docker compose.",
            ),
        )
        store.insert(unit)

        # A lone double-quote normalises to '"' after strip/lower.
        # Must not crash, and FTS-discoverable results must still appear.
        results = store.query(['"', "stripe-mock"])
        assert len(results) == 1
        assert results[0].id == unit.id

    @pytest.mark.parametrize(
        "malicious_domain",
        [
            '"""',  # Multiple consecutive quotes.
            'term"OR"1"OR"',  # Attempt to inject FTS OR operator.
            'a\\"b',  # Backslash before quote.
            '") OR (id:',  # Attempt column filter injection.
            "term*",  # FTS5 prefix wildcard.
            "{near term}",  # FTS5 NEAR syntax.
            "^boost",  # FTS5 boost operator.
            "",  # Empty after normalisation.
        ],
        ids=[
            "consecutive_quotes",
            "or_injection",
            "backslash_quote",
            "column_filter_injection",
            "prefix_wildcard",
            "near_syntax",
            "boost_operator",
            "empty_string",
        ],
    )
    def test_fts_query_with_malicious_domain(self, store: LocalStore, malicious_domain: str):
        """FTS-only results must not be lost when a query includes a hostile term."""
        unit = _make_unit(
            domain=["ci"],
            insight=Insight(
                summary="The stripe-mock server requires Docker",
                detail="Run stripe-mock in Docker for integration tests.",
                action="Use docker compose.",
            ),
        )
        store.insert(unit)

        results = store.query(["stripe-mock", malicious_domain])
        assert len(results) == 1
        assert results[0].id == unit.id

    def test_fts_query_empty_match_expr_does_not_crash(self, store: LocalStore):
        """Query where all terms produce an empty FTS expression must not crash.

        Domain normalisation passes these terms through (they are non-empty
        after strip/lower), but _build_fts_match_expr strips the quotes and
        produces an empty expression. The query should return empty (no domain
        or FTS match), not crash.
        """
        unit = _make_unit(
            domain=["ci"],
            insight=Insight(
                summary="Docker required",
                detail="Detail.",
                action="Action.",
            ),
        )
        store.insert(unit)

        results = store.query(['"', '""'])
        assert results == []

    def test_fts_updated_after_unit_update(self, store: LocalStore):
        unit = _make_unit(
            domain=["ci"],
            insight=Insight(
                summary="Old summary about webpack",
                detail="Old detail.",
                action="Old action.",
            ),
        )
        store.insert(unit)

        updated = unit.model_copy(
            update={
                "insight": Insight(
                    summary="New summary about vite bundler",
                    detail="New detail.",
                    action="New action.",
                )
            }
        )
        store.update(updated)

        assert store.query(["webpack"]) == []
        results = store.query(["vite"])
        assert len(results) == 1
        assert results[0].id == unit.id


class TestDomainNormalisation:
    def test_stores_domains_as_lowercase(self, store: LocalStore):
        unit = _make_unit(domain=["API", "Payments"])
        store.insert(unit)
        domains = _inspect_domains(store.db_path, unit.id)
        assert domains == ["api", "payments"]

    def test_strips_whitespace_from_domains(self, store: LocalStore):
        unit = _make_unit(domain=["  api  ", "payments "])
        store.insert(unit)
        domains = _inspect_domains(store.db_path, unit.id)
        assert domains == ["api", "payments"]

    def test_case_insensitive_query(self, store: LocalStore):
        unit = _make_unit(domain=["API", "Payments"])
        store.insert(unit)

        results = store.query(["api"])
        assert len(results) == 1
        assert results[0].id == unit.id

    def test_mixed_case_query_matches(self, store: LocalStore):
        unit = _make_unit(domain=["databases"])
        store.insert(unit)

        results = store.query(["Databases"])
        assert len(results) == 1
        assert results[0].id == unit.id

    def test_deduplicates_after_normalisation(self, store: LocalStore):
        unit = _make_unit(domain=["API", "api", "Api"])
        store.insert(unit)
        domains = _inspect_domains(store.db_path, unit.id)
        assert domains == ["api"]

    def test_filters_empty_and_whitespace_domains(self, store: LocalStore):
        unit = _make_unit(domain=["api", "  ", ""])
        store.insert(unit)
        domains = _inspect_domains(store.db_path, unit.id)
        assert domains == ["api"]

    def test_normalised_domains_persisted_in_blob(self, store: LocalStore):
        unit = _make_unit(domain=["API", "Payments"])
        store.insert(unit)
        retrieved = store.get(unit.id)
        assert retrieved is not None
        assert retrieved.domain == ["api", "payments"]

    def test_query_with_whitespace_only_domains_returns_empty(self, store: LocalStore):
        unit = _make_unit(domain=["databases"])
        store.insert(unit)
        results = store.query(["  ", ""])
        assert results == []


class TestEndToEnd:
    def test_insert_confirm_query_flag_lifecycle(self, store: LocalStore):
        unit = _make_unit(
            domain=["api", "payments"],
            context=Context(languages=["python"], frameworks=["fastapi"]),
        )
        store.insert(unit)

        results = store.query(["api", "payments"], language="python")
        assert len(results) == 1
        assert results[0].evidence.confidence == 0.5

        confirmed = apply_confirmation(results[0])
        store.update(confirmed)
        results = store.query(["api", "payments"])
        assert results[0].evidence.confidence == pytest.approx(0.6)
        assert results[0].evidence.confirmations == 2

        flagged = apply_flag(results[0], FlagReason.STALE)
        store.update(flagged)
        results = store.query(["api", "payments"])
        assert results[0].evidence.confidence == pytest.approx(0.45)
        assert len(results[0].flags) == 1

    def test_context_manager_lifecycle(self, tmp_path: Path):
        db_path = tmp_path / "lifecycle.db"
        unit = _make_unit(domain=["testing"])

        with LocalStore(db_path=db_path) as store:
            store.insert(unit)

        with LocalStore(db_path=db_path) as store:
            retrieved = store.get(unit.id)
            assert retrieved == unit


class TestStats:
    def test_empty_store_returns_zero_counts(self, store: LocalStore):
        result = store.stats()
        assert result.total_count == 0
        assert result.domain_counts == {}
        assert result.recent == []
        assert result.confidence_distribution == {
            "0.0-0.3": 0,
            "0.3-0.5": 0,
            "0.5-0.7": 0,
            "0.7-1.0": 0,
        }

    def test_total_count_matches_inserted_units(self, store: LocalStore):
        for _ in range(3):
            store.insert(_make_unit(domain=["api"]))
        result = store.stats()
        assert result.total_count == 3

    def test_domain_counts_across_multiple_units(self, store: LocalStore):
        store.insert(_make_unit(domain=["api", "payments"]))
        store.insert(_make_unit(domain=["api", "databases"]))
        store.insert(_make_unit(domain=["databases"]))
        result = store.stats()
        assert result.domain_counts == {"api": 2, "databases": 2, "payments": 1}

    def test_recent_ordered_by_last_confirmed_descending(self, store: LocalStore):
        now = datetime.now(UTC)
        old_unit = _make_unit(
            domain=["api"],
            context=Context(languages=["python"]),
        )
        old_unit = old_unit.model_copy(
            update={
                "evidence": Evidence(
                    first_observed=now - timedelta(days=10),
                    last_confirmed=now - timedelta(days=10),
                ),
            },
        )
        new_unit = _make_unit(
            domain=["api"],
            context=Context(languages=["go"]),
        )
        new_unit = new_unit.model_copy(
            update={
                "evidence": Evidence(
                    first_observed=now - timedelta(days=1),
                    last_confirmed=now - timedelta(days=1),
                ),
            },
        )
        store.insert(old_unit)
        store.insert(new_unit)

        result = store.stats()
        assert len(result.recent) == 2
        assert result.recent[0].id == new_unit.id
        assert result.recent[1].id == old_unit.id

    def test_recent_respects_limit(self, store: LocalStore):
        for _ in range(10):
            store.insert(_make_unit(domain=["api"]))
        result = store.stats(recent_limit=3)
        assert len(result.recent) == 3

    def test_confidence_distribution_buckets(self, store: LocalStore):
        # Default confidence is 0.5, which falls in "0.5-0.7".
        unit_mid = _make_unit(domain=["api"])
        store.insert(unit_mid)

        # Confirm twice to reach 0.7, which falls in "0.7-1.0".
        high_unit = _make_unit(domain=["api"])
        store.insert(high_unit)
        confirmed = apply_confirmation(high_unit)
        confirmed = apply_confirmation(confirmed)
        store.update(confirmed)

        # Flag twice to reach 0.2, which falls in "0.0-0.3".
        low_unit = _make_unit(domain=["api"])
        store.insert(low_unit)
        flagged = apply_flag(low_unit, FlagReason.STALE)
        flagged = apply_flag(flagged, FlagReason.STALE)
        store.update(flagged)

        # Flag once to reach 0.35, which falls in "0.3-0.5".
        mid_low_unit = _make_unit(domain=["api"])
        store.insert(mid_low_unit)
        flagged_once = apply_flag(mid_low_unit, FlagReason.STALE)
        store.update(flagged_once)

        result = store.stats()
        assert result.confidence_distribution == {
            "0.0-0.3": 1,
            "0.3-0.5": 1,
            "0.5-0.7": 1,
            "0.7-1.0": 1,
        }

    def test_stats_rejects_negative_recent_limit(self, store: LocalStore):
        with pytest.raises(ValueError, match="recent_limit must be non-negative"):
            store.stats(recent_limit=-1)

    def test_stats_allows_zero_recent_limit(self, store: LocalStore):
        store.insert(_make_unit(domain=["api"]))
        result = store.stats(recent_limit=0)
        assert result.total_count == 1
        assert result.recent == []

    def test_stats_raises_when_store_closed(self, tmp_path: Path):
        s = LocalStore(db_path=tmp_path / "test.db")
        s.close()
        with pytest.raises(RuntimeError, match="LocalStore is closed"):
            s.stats()


class TestAll:
    def test_all_returns_empty_list_for_empty_store(self, store: LocalStore) -> None:
        assert store.all() == []

    def test_all_returns_all_inserted_units(self, store: LocalStore) -> None:
        u1 = _make_unit(domain=["api"])
        u2 = _make_unit(domain=["databases"])
        store.insert(u1)
        store.insert(u2)
        result = store.all()
        ids = {u.id for u in result}
        assert ids == {u1.id, u2.id}

    def test_all_raises_when_store_closed(self, store: LocalStore) -> None:
        store.close()
        with pytest.raises(RuntimeError, match="closed"):
            store.all()


class TestPendingSyncUnits:
    def test_returns_only_pending_units(self, store: LocalStore) -> None:
        pending = _make_unit(domain=["api"])
        synced = _make_unit(domain=["databases"])
        store.insert(pending, team_sync_status=TeamSyncStatus.PENDING)
        store.insert(synced, team_sync_status=TeamSyncStatus.SYNCED)

        results = store.pending_sync_units()

        assert [unit.id for unit in results] == [pending.id]

    def test_pending_sync_units_raises_when_store_closed(self, store: LocalStore) -> None:
        store.close()
        with pytest.raises(RuntimeError, match="closed"):
            store.pending_sync_units()


class TestDelete:
    def test_delete_removes_unit(self, store: LocalStore) -> None:
        unit = _make_unit(domain=["api"])
        store.insert(unit)
        store.delete(unit.id)
        assert store.get(unit.id) is None

    def test_delete_removes_domain_tags(self, store: LocalStore) -> None:
        unit = _make_unit(domain=["api", "payments"])
        store.insert(unit)
        store.delete(unit.id)
        domains = _inspect_domains(store.db_path, unit.id)
        assert domains == []

    def test_delete_removes_fts_entry(self, store: LocalStore) -> None:
        unit = _make_unit(domain=["api"])
        store.insert(unit)
        store.delete(unit.id)
        # Query by summary text should return nothing.
        results = store.query(["api"])
        assert len(results) == 0

    def test_delete_missing_unit_raises_key_error(self, store: LocalStore) -> None:
        with pytest.raises(KeyError, match="ku_nonexistent"):
            store.delete("ku_nonexistent")

    def test_delete_raises_when_store_closed(self, store: LocalStore) -> None:
        store.close()
        with pytest.raises(RuntimeError, match="closed"):
            store.delete("ku_any")


class TestDefaultDbPath:
    """Tests for XDG Base Directory spec compliance."""

    def test_uses_xdg_data_home_when_set(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "custom-data"))
        result = _default_db_path()
        assert result == tmp_path / "custom-data" / "cq" / "local.db"

    def test_falls_back_to_dot_local_share(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        result = _default_db_path()
        assert result == Path.home() / ".local" / "share" / "cq" / "local.db"

    def test_ignores_relative_xdg_data_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", "./relative/path")
        result = _default_db_path()
        assert result == Path.home() / ".local" / "share" / "cq" / "local.db"


class TestMigrateLegacyDb:
    """Tests for automatic migration from ~/.cq/local.db."""

    def test_migrates_legacy_db_to_new_path(self, tmp_path: Path) -> None:
        legacy_dir = tmp_path / ".cq"
        legacy_dir.mkdir()
        legacy_db = legacy_dir / "local.db"
        legacy_db.write_text("fake-db")

        new_path = tmp_path / "share" / "cq" / "local.db"

        with patch("cq_mcp.local_store._LEGACY_DB_PATH", legacy_db):
            _migrate_legacy_db(new_path)

        assert new_path.exists()
        assert new_path.read_text() == "fake-db"
        assert not legacy_db.exists()
        # Legacy directory removed because it was empty.
        assert not legacy_dir.exists()

    def test_migrates_wal_and_shm_files(self, tmp_path: Path) -> None:
        legacy_dir = tmp_path / ".cq"
        legacy_dir.mkdir()
        legacy_db = legacy_dir / "local.db"
        legacy_db.write_text("fake-db")
        (legacy_dir / "local.db-wal").write_text("wal-data")
        (legacy_dir / "local.db-shm").write_text("shm-data")

        new_path = tmp_path / "share" / "cq" / "local.db"

        with patch("cq_mcp.local_store._LEGACY_DB_PATH", legacy_db):
            _migrate_legacy_db(new_path)

        assert new_path.exists()
        assert Path(str(new_path) + "-wal").read_text() == "wal-data"
        assert Path(str(new_path) + "-shm").read_text() == "shm-data"

    def test_no_op_when_legacy_does_not_exist(self, tmp_path: Path) -> None:
        legacy_db = tmp_path / ".cq" / "local.db"
        new_path = tmp_path / "share" / "cq" / "local.db"

        with patch("cq_mcp.local_store._LEGACY_DB_PATH", legacy_db):
            _migrate_legacy_db(new_path)

        assert not new_path.exists()

    def test_prefers_xdg_when_both_exist(self, tmp_path: Path) -> None:
        legacy_dir = tmp_path / ".cq"
        legacy_dir.mkdir()
        legacy_db = legacy_dir / "local.db"
        legacy_db.write_text("old-db")

        new_dir = tmp_path / "share" / "cq"
        new_dir.mkdir(parents=True)
        new_path = new_dir / "local.db"
        new_path.write_text("new-db")

        with patch("cq_mcp.local_store._LEGACY_DB_PATH", legacy_db):
            _migrate_legacy_db(new_path)

        # XDG path is unchanged; legacy is not deleted.
        assert new_path.read_text() == "new-db"
        assert legacy_db.read_text() == "old-db"

    def test_migration_failure_does_not_crash(self, tmp_path: Path) -> None:
        legacy_dir = tmp_path / ".cq"
        legacy_dir.mkdir()
        legacy_db = legacy_dir / "local.db"
        legacy_db.write_text("fake-db")

        new_path = tmp_path / "share" / "cq" / "local.db"

        with (
            patch("cq_mcp.local_store._LEGACY_DB_PATH", legacy_db),
            patch("cq_mcp.local_store.shutil.move", side_effect=OSError("cross-device link")),
        ):
            _migrate_legacy_db(new_path)

        # Legacy DB untouched; no crash.
        assert legacy_db.read_text() == "fake-db"
        assert not new_path.exists()

    def test_keeps_legacy_dir_when_not_empty(self, tmp_path: Path) -> None:
        legacy_dir = tmp_path / ".cq"
        legacy_dir.mkdir()
        legacy_db = legacy_dir / "local.db"
        legacy_db.write_text("fake-db")
        (legacy_dir / "other-file.txt").write_text("keep me")

        new_path = tmp_path / "share" / "cq" / "local.db"

        with patch("cq_mcp.local_store._LEGACY_DB_PATH", legacy_db):
            _migrate_legacy_db(new_path)

        assert new_path.exists()
        assert not legacy_db.exists()
        # Directory kept because it still has other files.
        assert legacy_dir.exists()
        assert (legacy_dir / "other-file.txt").exists()
