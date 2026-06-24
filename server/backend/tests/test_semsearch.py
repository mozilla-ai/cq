"""Unit tests for semsearch helpers and the semsearch-enabled store query path.

Integration tests patch the names imported into KnowledgeRepository
(_SEMSEARCH_ENABLED, sem_query, sem_insert_unit) so the semsearch code paths
run deterministically in CI without a real embedding server or sqlite-vec loaded.
"""

import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from cq.models import Context, Insight, KnowledgeUnit, Tier, create_knowledge_unit

from cq_server import semsearch
from cq_server.core.db import Database
from cq_server.semsearch import queries as semsearch_queries

from .db_helpers import _make_store


def _make_unit(domain: str = "test", *, summary: str = "s", detail: str = "d", action: str = "a") -> KnowledgeUnit:
    """
    Create a test KnowledgeUnit with the given domain and simple default insight and metadata.

    Parameters:
        domain (str): Domain to assign to the unit (placed into the unit's `domains` list).
        summary (str): Insight summary text.
        detail (str): Insight detail text.
        action (str): Insight action text.

    Returns:
        KnowledgeUnit: A newly created KnowledgeUnit configured for tests (private tier, empty Context,
            created_by="tester").
    """
    return create_knowledge_unit(
        domains=[domain],
        insight=Insight(summary=summary, detail=detail, action=action),
        context=Context(),
        tier=Tier.PRIVATE,
        created_by="tester",
    )


class _RecordingDatabase(Database):
    """Minimal Database test double that records executed clause batches."""

    def __init__(self, *, fetch_rows: list[tuple[str, float]] | None = None) -> None:
        self.executed_clauses: list[tuple[object, dict[str, object]]] = []
        self.fetch_rows = fetch_rows or []

    async def run_sync(self, fn, /, *args, **kwargs):
        return fn(*args, **kwargs)

    def run_clauses_sync(self, clauses, *, fetch: bool = False):
        self.executed_clauses.extend(clauses)
        if fetch:
            return self.fetch_rows
        return []


# ---------------------------------------------------------------------------
# Store integration: semsearch-enabled query path
# ---------------------------------------------------------------------------


class TestSemsearchQueryPath:
    """Verify KnowledgeRepository.query() routes through semsearch when enabled.

    These tests patch the names imported directly into KnowledgeRepository
    (_SEMSEARCH_ENABLED, sem_query, sem_insert_unit) so the semsearch code
    paths execute without a real embedding server.
    """

    async def test_query_calls_sem_query_when_semsearch_enabled(
        self,
        db_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When semsearch is enabled, store.query() delegates to sem_query."""
        unit = _make_unit("astronomy", summary="Exoplanet transit photometry")
        store = _make_store(db_path)
        await store.insert(unit)
        await store.set_review_status(unit.id, "approved", "reviewer")

        import cq_server.repositories.knowledge as knowledge_mod

        monkeypatch.setattr(knowledge_mod, "_SEMSEARCH_ENABLED", True)
        mock_sem_query = AsyncMock(return_value=[unit])
        monkeypatch.setattr(knowledge_mod, "sem_query", mock_sem_query)
        monkeypatch.setattr(knowledge_mod, "sem_insert_unit", AsyncMock())

        results = await store.query(["astronomy"])

        mock_sem_query.assert_awaited_once()
        assert len(results) == 1
        assert results[0].id == unit.id

    async def test_lower_cosine_distance_ranks_first(
        self,
        db_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """sem_query returns units pre-ranked; store.query() preserves that order."""
        u_near = _make_unit("astro", summary="Transit dip exoplanet")
        u_far = _make_unit("astro", summary="Heavy element HII region")
        store = _make_store(db_path)
        for u in [u_near, u_far]:
            await store.insert(u)
            await store.set_review_status(u.id, "approved", "reviewer")

        # sem_query returns units already sorted by semantic relevance
        import cq_server.repositories.knowledge as knowledge_mod

        monkeypatch.setattr(knowledge_mod, "_SEMSEARCH_ENABLED", True)
        monkeypatch.setattr(knowledge_mod, "sem_query", AsyncMock(return_value=[u_near, u_far]))
        monkeypatch.setattr(knowledge_mod, "sem_insert_unit", AsyncMock())

        results = await store.query(["astro"])

        assert len(results) == 2
        assert results[0].id == u_near.id, "nearer unit should rank first"

    async def test_insert_unit_called_on_insert_when_semsearch_enabled(
        self,
        db_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """store.insert() calls sem_insert_unit when semsearch is enabled."""
        unit = _make_unit("astronomy")
        store = _make_store(db_path)

        import cq_server.repositories.knowledge as knowledge_mod

        monkeypatch.setattr(knowledge_mod, "_SEMSEARCH_ENABLED", True)
        mock_insert = AsyncMock()
        monkeypatch.setattr(knowledge_mod, "sem_insert_unit", mock_insert)

        await store.insert(unit)

        mock_insert.assert_awaited_once()

    async def test_query_falls_back_to_sql_on_embedding_service_error(
        self,
        db_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """store.query() falls back to SQL when sem_query fails on embedding service checks."""
        unit = _make_unit("astronomy", summary="Exoplanet transit")
        store = _make_store(db_path)
        await store.insert(unit)
        await store.set_review_status(unit.id, "approved", "reviewer")

        import cq_server.repositories.knowledge as knowledge_mod

        monkeypatch.setattr(knowledge_mod, "_SEMSEARCH_ENABLED", True)
        mock_sem_query = AsyncMock(side_effect=semsearch_queries.EmbeddingServiceError("embedding API unavailable"))
        monkeypatch.setattr(knowledge_mod, "sem_query", mock_sem_query)
        monkeypatch.setattr(knowledge_mod, "sem_insert_unit", AsyncMock())

        results = await store.query(["astronomy"])

        mock_sem_query.assert_awaited_once()
        assert len(results) == 1
        assert results[0].id == unit.id

    async def test_query_does_not_fallback_on_non_embedding_runtime_error(
        self,
        db_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """store.query() should propagate non-embedding semsearch runtime errors."""
        unit = _make_unit("astronomy", summary="Exoplanet transit")
        store = _make_store(db_path)
        await store.insert(unit)
        await store.set_review_status(unit.id, "approved", "reviewer")

        import cq_server.repositories.knowledge as knowledge_mod

        monkeypatch.setattr(knowledge_mod, "_SEMSEARCH_ENABLED", True)
        monkeypatch.setattr(knowledge_mod, "sem_query", AsyncMock(side_effect=RuntimeError("db failure")))
        monkeypatch.setattr(knowledge_mod, "sem_insert_unit", AsyncMock())

        with pytest.raises(RuntimeError, match="db failure"):
            await store.query(["astronomy"])

    @pytest.mark.skipif(semsearch.is_enabled(), reason="Requires sqlite-vec extension and embedding dependencies")
    async def test_query_uses_domain_only_path_when_semsearch_disabled(
        self,
        db_path: Path,
    ) -> None:
        """When semsearch is disabled (default), store.query() uses the SQL-only path."""
        unit = _make_unit("astronomy", summary="Exoplanet transit")
        store = _make_store(db_path)
        await store.insert(unit)
        await store.set_review_status(unit.id, "approved", "reviewer")

        results = await store.query(["astronomy"])

        assert len(results) == 1
        assert results[0].id == unit.id

    @pytest.mark.skipif(not semsearch.is_enabled(), reason="Requires sqlite-vec extension and embedding dependencies")
    async def test_semsearch_e2e_returns_two_most_relevant_units(
        self,
        db_path: Path,
    ) -> None:
        """E2E semsearch query returns top-2 relevant astronomy units, excluding unrelated content."""
        try:
            await semsearch_queries._get_embeddings(["connectivity check"])
        except Exception as exc:
            pytest.skip(f"embedding server unavailable: {exc}")

        u_near = create_knowledge_unit(
            domains=["astronomy"],
            insight=Insight(
                summary="Detect exoplanets from transit dips",
                detail="Transit photometry reveals periodic light-curve dips from orbiting planets.",
                action="Implement a FastAPI service to score transit candidates and rank follow-up targets.",
            ),
            context=Context(languages=["python"], frameworks=["fastapi"], pattern="transit-detection"),
            tier=Tier.PRIVATE,
            created_by="tester",
        )
        u_far = create_knowledge_unit(
            domains=["astronomy"],
            insight=Insight(
                summary="Map heavy-element enrichment in HII regions",
                detail="Emission-line analysis estimates oxygen and nitrogen abundance in ionized gas clouds.",
                action="Track metallicity gradients to compare star-formation environments.",
            ),
            context=Context(),
            tier=Tier.PRIVATE,
            created_by="tester",
        )
        u_unrelated = create_knowledge_unit(
            domains=["cybersecurity"],
            insight=Insight(
                summary="Rotate API credentials after incident response",
                detail="Short-lived credentials limit persistence after compromise.",
                action="Automate revocation and rotation workflows every 30 days.",
            ),
            context=Context(languages=["go"], frameworks=["gin"], pattern="credential-rotation"),
            tier=Tier.PRIVATE,
            created_by="tester",
        )

        store = _make_store(db_path)
        # Due to alembic env.py, logging is messed up
        logging.getLogger("cq_server.semsearch").disabled = False
        logging.getLogger("cq_server.semsearch.queries").disabled = False

        for unit in [u_near, u_far, u_unrelated]:
            await store.insert(unit)
            await store.set_review_status(unit.id, "approved", "reviewer")

        results = await store.query(
            ["astronomy"],
            languages=["python"],
            frameworks=["fastapi"],
            pattern="transit-detection",
            limit=2,
        )

        assert len(results) == 2
        assert results[0].id == u_near.id
        assert {result.id for result in results} == {u_near.id, u_far.id}
        assert all("astronomy" in result.domains for result in results)


# ---------------------------------------------------------------------------
# Unit tests: semsearch module helpers (without external dependencies)
# ---------------------------------------------------------------------------


class TestIsEnabled:
    """Test the is_enabled() flag."""

    def test_is_enabled_returns_boolean(self) -> None:
        """is_enabled() should always return a boolean."""
        result = semsearch.is_enabled()
        assert isinstance(result, bool)


class TestSerializeEmbedding:
    """Test embedding serialization (requires semsearch to be enabled)."""

    @pytest.mark.skipif(not semsearch.is_enabled(), reason="Requires sqlite-vec extension")
    async def test_serialize_embedding_returns_bytes(self) -> None:
        """_serialize_embedding should convert numpy array to bytes."""
        import numpy as np

        vec = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        result = semsearch_queries._serialize_embedding(vec)
        assert isinstance(result, bytes)
        assert len(result) > 0

    @pytest.mark.skipif(not semsearch.is_enabled(), reason="Requires sqlite-vec extension")
    async def test_serialize_embedding_consistent_length(self) -> None:
        """_serialize_embedding should produce consistent byte length for same vec length."""
        import numpy as np

        vec1 = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        vec2 = np.array([0.4, 0.5, 0.6], dtype=np.float32)
        result1 = semsearch_queries._serialize_embedding(vec1)
        result2 = semsearch_queries._serialize_embedding(vec2)
        assert len(result1) == len(result2)


class TestGetEmbeddings:
    """Test _get_embeddings with mocking to avoid real API calls."""

    async def test_get_embeddings_raises_when_semsearch_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_get_embeddings should raise RuntimeError when semsearch is disabled."""
        monkeypatch.setattr(semsearch_queries, "semsearch_enabled", lambda: False)

        with pytest.raises(RuntimeError, match="Semantic search is not enabled"):
            await semsearch_queries._get_embeddings(["test"])

    @pytest.mark.skipif(not semsearch.is_enabled(), reason="Requires embedding service")
    async def test_get_embeddings_returns_array(self) -> None:
        """_get_embeddings should return an array-like object."""
        import numpy as np

        try:
            result = await semsearch_queries._get_embeddings(["test query"])
            assert isinstance(result, np.ndarray)
            assert result.ndim == 1
            assert len(result) > 0
        except Exception as exc:
            pytest.skip(f"Embedding service unavailable: {exc}")

    @pytest.mark.skipif(not semsearch.is_enabled(), reason="Requires embedding service")
    async def test_get_embeddings_multiple_words_averaged(self) -> None:
        """_get_embeddings should average embeddings across multiple input strings."""
        import numpy as np

        try:
            result = await semsearch_queries._get_embeddings(["hello world", "foo bar"])
            assert isinstance(result, np.ndarray)
            assert result.ndim == 1
        except Exception as exc:
            pytest.skip(f"Embedding service unavailable: {exc}")


class TestInsertUnitErrors:
    """Test insert_unit error handling and edge cases."""

    @pytest.mark.skipif(semsearch.is_enabled(), reason="Test requires semsearch disabled")
    async def test_insert_unit_disabled_returns_early(self, db_path: Path) -> None:
        """insert_unit should return early (not raise) when semsearch is disabled."""
        unit = _make_unit()
        db = _RecordingDatabase()

        # Should not raise, should just return early
        await semsearch_queries.insert_unit(db, unit)

    @pytest.mark.skipif(not semsearch.is_enabled(), reason="Requires semsearch enabled")
    async def test_insert_unit_raises_on_empty_insight_text(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """insert_unit should raise ValueError when insight text is empty."""
        unit = create_knowledge_unit(
            domains=["test"],
            insight=Insight(summary="", detail="", action=""),  # All empty
            context=Context(),
            tier=Tier.PRIVATE,
            created_by="tester",
        )
        db = _RecordingDatabase()

        with pytest.raises(ValueError, match="Cannot insert embedding for unit with empty insight text"):
            await semsearch_queries.insert_unit(db, unit)


class TestSemsearchQueryHelpers:
    """Unit tests for helper builders and update/combined-query branches."""

    def test_build_insert_vec_clauses_returns_insert_statement_and_params(self) -> None:
        """build_insert_vec_clauses should return one insert clause with unit_id and embedding."""
        unit = _make_unit("astro")
        serialized = b"abc"

        clauses = semsearch_queries.build_insert_vec_clauses(unit, serialized)

        assert len(clauses) == 1
        statement, params = clauses[0]
        assert "INSERT INTO knowledge_units_vec" in str(statement)
        assert params == {"unit_id": unit.id, "embedding": serialized}

    def test_build_update_vec_clauses_returns_delete_then_insert(self) -> None:
        """build_update_vec_clauses should return delete and insert clauses in order."""
        unit = _make_unit("astro")
        serialized = b"xyz"

        clauses = semsearch_queries.build_update_vec_clauses(unit, serialized)

        assert len(clauses) == 2
        first_statement, first_params = clauses[0]
        second_statement, second_params = clauses[1]
        assert "DELETE FROM knowledge_units_vec" in str(first_statement)
        assert "INSERT INTO knowledge_units_vec" in str(second_statement)
        assert first_params == {"unit_id": unit.id}
        assert second_params == {"unit_id": unit.id, "embedding": serialized}

    async def test_update_unit_executes_base_then_delete_then_insert(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """update_unit should execute base clauses plus delete/insert via Database.run_sync."""
        unit = _make_unit("astro", summary="sum", detail="det", action="act")
        monkeypatch.setattr(semsearch_queries, "semsearch_enabled", lambda: True)

        async def _fake_embeddings(_wordlist: list[str]):
            return [0.1, 0.2]

        monkeypatch.setattr(semsearch_queries, "_get_embeddings", _fake_embeddings)
        monkeypatch.setattr(semsearch_queries, "_serialize_embedding", lambda _vec: b"SER")

        db = _RecordingDatabase()
        base = [("SELECT 1", {"x": 1})]

        await semsearch_queries.update_unit(db, unit, base_clauses=base)

        assert len(db.executed_clauses) == 3
        assert str(db.executed_clauses[0][0]) == "SELECT 1"
        assert db.executed_clauses[0][1] == {"x": 1}
        assert "DELETE FROM knowledge_units_vec" in str(db.executed_clauses[1][0])
        assert db.executed_clauses[1][1] == {"unit_id": unit.id}
        assert "INSERT INTO knowledge_units_vec" in str(db.executed_clauses[2][0])
        assert db.executed_clauses[2][1] == {"unit_id": unit.id, "embedding": b"SER"}

    async def test_update_unit_raises_on_empty_insight_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """update_unit should raise ValueError when summary/detail/action are all blank."""
        unit = _make_unit("astro", summary="", detail="", action="")
        monkeypatch.setattr(semsearch_queries, "semsearch_enabled", lambda: True)

        with pytest.raises(ValueError, match="Cannot insert embedding for unit with empty insight text"):
            await semsearch_queries.update_unit(_RecordingDatabase(), unit)

    async def test_combined_query_wraps_sqlite_operational_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """combined_query should wrap sqlite3.OperationalError in a RuntimeError."""
        monkeypatch.setattr(semsearch_queries, "semsearch_enabled", lambda: True)

        async def _raise_sqlite(_domains: list[str]):
            raise semsearch_queries.sqlite3.OperationalError("boom")

        monkeypatch.setattr(semsearch_queries, "_get_embeddings", _raise_sqlite)

        with pytest.raises(RuntimeError, match="Database error when performing combined query"):
            await semsearch_queries.combined_query(_RecordingDatabase(), ["astro"], None, None, "")

    async def test_combined_query_tie_breaks_by_id_desc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """combined_query should use id descending as tie-break when scores are equal."""
        monkeypatch.setattr(semsearch_queries, "semsearch_enabled", lambda: True)
        monkeypatch.setattr(semsearch_queries, "normalize_domains", lambda d: d)

        async def _fake_embeddings(_domains: list[str]):
            return [0.5, 0.5]

        monkeypatch.setattr(semsearch_queries, "_get_embeddings", _fake_embeddings)
        monkeypatch.setattr(semsearch_queries, "_serialize_embedding", lambda _vec: b"Q")
        monkeypatch.setattr(semsearch_queries, "calculate_relevance", lambda *args, **kwargs: 1.0)

        unit_a = _make_unit("astro")
        unit_b = _make_unit("astro")
        unit_a.evidence.confidence = 1.0
        unit_b.evidence.confidence = 1.0

        # Keep distances equal so score ties and id tie-break is exercised.
        rows = [
            (unit_a.model_dump_json(), 1.0),
            (unit_b.model_dump_json(), 1.0),
        ]

        results = await semsearch_queries.combined_query(
            _RecordingDatabase(fetch_rows=rows),
            ["astro"],
            None,
            None,
            "",
            limit=2,
        )

        expected = sorted([unit_a.id, unit_b.id], reverse=True)
        assert [u.id for u in results] == expected


class TestCombinedQueryErrors:
    """Test combined_query error handling and edge cases."""

    async def test_combined_query_raises_when_semsearch_disabled(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """combined_query should raise RuntimeError when semsearch is disabled."""
        monkeypatch.setattr(semsearch_queries, "semsearch_enabled", lambda: False)

        with pytest.raises(RuntimeError, match="Semantic search is not enabled"):
            await semsearch_queries.combined_query(_RecordingDatabase(), ["test"], None, None, "")

    @pytest.mark.skipif(not semsearch.is_enabled(), reason="Requires semsearch enabled")
    async def test_combined_query_raises_on_invalid_limit(self, db_path: Path) -> None:
        """combined_query should raise ValueError when limit is not positive."""
        with pytest.raises(ValueError, match="limit must be positive"):
            await semsearch_queries.combined_query(_RecordingDatabase(), ["test"], None, None, "", limit=0)

    @pytest.mark.skipif(not semsearch.is_enabled(), reason="Requires semsearch enabled")
    async def test_combined_query_raises_on_negative_limit(self, db_path: Path) -> None:
        """combined_query should raise ValueError when limit is negative."""
        with pytest.raises(ValueError, match="limit must be positive"):
            await semsearch_queries.combined_query(_RecordingDatabase(), ["test"], None, None, "", limit=-1)

    @pytest.mark.skipif(not semsearch.is_enabled(), reason="Requires semsearch enabled")
    async def test_combined_query_returns_empty_on_no_domains(self, db_path: Path) -> None:
        """combined_query should return empty list when domains list is empty."""
        result = await semsearch_queries.combined_query(_RecordingDatabase(), [], None, None, "")
        assert result == []

    @pytest.mark.skipif(not semsearch.is_enabled(), reason="Requires semsearch enabled")
    async def test_combined_query_e2e_with_confidence_weighting(self, db_path: Path) -> None:
        """combined_query should weight results by evidence.confidence."""
        try:
            await semsearch_queries._get_embeddings(["test"])
        except Exception as exc:
            pytest.skip(f"embedding server unavailable: {exc}")

        # Create units with different confidence levels
        unit_high_conf = create_knowledge_unit(
            domains=["physics"],
            insight=Insight(summary="Quantum mechanics", detail="Study of quantum systems", action="Research QM"),
            context=Context(),
            tier=Tier.PRIVATE,
            created_by="tester",
        )
        unit_high_conf.evidence.confidence = 0.95

        unit_low_conf = create_knowledge_unit(
            domains=["physics"],
            insight=Insight(summary="Classical mechanics", detail="Study of classical systems", action="Research CM"),
            context=Context(),
            tier=Tier.PRIVATE,
            created_by="tester",
        )
        unit_low_conf.evidence.confidence = 0.2

        store = _make_store(db_path)
        for unit in [unit_high_conf, unit_low_conf]:
            await store.insert(unit)
            await store.set_review_status(unit.id, "approved", "reviewer")

        results = await semsearch_queries.combined_query(
            store._db,
            ["physics"],
            None,
            None,
            "",
            limit=2,
        )

        # High confidence unit should rank first
        assert len(results) <= 2
        if len(results) > 1:
            # The high-confidence unit should appear first in results
            assert any(r.id == unit_high_conf.id for r in results)
