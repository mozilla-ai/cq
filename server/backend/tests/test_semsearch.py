"""Unit tests for semsearch helpers and the semsearch-enabled store query path.

Pure-Python helpers (build_field_logits, compute_combined_relevance) are tested
without any external dependencies.

Integration tests patch the names imported into KnowledgeRepository
(_SEMSEARCH_ENABLED, sem_query, sem_insert_unit) so the semsearch code paths
run deterministically in CI without a real embedding server or sqlite-vec loaded.
"""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import logging
from cq.models import Context, Insight, KnowledgeUnit, Tier, create_knowledge_unit

from cq_server import semsearch
from cq_server.semsearch import queries as semsearch_queries

from .db_helpers import _make_store


def _make_unit(domain: str = "test", *, summary: str = "s", detail: str = "d", action: str = "a") -> KnowledgeUnit:
    return create_knowledge_unit(
        domains=[domain],
        insight=Insight(summary=summary, detail=detail, action=action),
        context=Context(),
        tier=Tier.PRIVATE,
        created_by="tester",
    )



# ---------------------------------------------------------------------------
# Pure-Python helper: build_field_logits
# ---------------------------------------------------------------------------


class TestBuildFieldLogits:
    def test_empty_input_returns_empty(self) -> None:
        assert semsearch_queries.build_field_logits({}) == {}

    def test_row_with_no_numeric_fields_returns_empty(self) -> None:
        result = semsearch_queries.build_field_logits({"a": ()})
        assert result == {}

    def test_uniform_values_produce_zero_logits(self) -> None:
        row_data = {"a": (1.0,), "b": (1.0,)}
        logits = semsearch_queries.build_field_logits(row_data, invert=True)
        assert 0 in logits
        for logit in logits[0].values():
            assert logit == 0.0

    def test_lower_distance_gets_positive_logit_when_inverted(self) -> None:
        row_data = {"near": (0.1,), "far": (0.9,)}
        logits = semsearch_queries.build_field_logits(row_data, invert=True)
        assert 0 in logits
        assert logits[0][0.1] > 0, "nearer unit should be boosted"
        assert logits[0][0.9] < 0, "farther unit should be diminished"
        assert logits[0][0.1] > logits[0][0.9]

    def test_non_inverted_higher_value_gets_higher_logit(self) -> None:
        row_data = {"low": (0.1,), "high": (0.9,)}
        logits = semsearch_queries.build_field_logits(row_data, invert=False)
        assert 0 in logits
        assert logits[0][0.9] > logits[0][0.1]


# ---------------------------------------------------------------------------
# Pure-Python helper: compute_combined_relevance
# ---------------------------------------------------------------------------


class TestComputeCombinedRelevance:
    def test_no_field_logits_returns_base_unchanged(self) -> None:
        result = semsearch_queries.compute_combined_relevance(0.5, (), {})
        assert result == 0.5

    def test_zero_logit_preserves_base(self) -> None:
        field_logits = {0: {0.5: 0.0}}
        result = semsearch_queries.compute_combined_relevance(0.5, (0.5,), field_logits)
        assert result == pytest.approx(0.5)

    def test_positive_logit_boosts_score(self) -> None:
        # logit=1.0 -> combined *= (1 + 1.0) = 2x base
        field_logits = {0: {0.1: 1.0}}
        result = semsearch_queries.compute_combined_relevance(0.5, (0.1,), field_logits)
        assert result == pytest.approx(1.0)

    def test_negative_logit_reduces_score(self) -> None:
        # logit=-0.5 -> combined *= (1 - 0.5) = 0.5x base
        field_logits = {0: {0.9: -0.5}}
        result = semsearch_queries.compute_combined_relevance(0.5, (0.9,), field_logits)
        assert result == pytest.approx(0.25)

    def test_missing_field_value_applies_neutral_modulation(self) -> None:
        # row_data has 0.9 but logit_map only has 0.3; missing key -> logit 0 -> no change
        field_logits = {0: {0.3: 0.5}}
        result = semsearch_queries.compute_combined_relevance(0.5, (0.9,), field_logits)
        assert result == pytest.approx(0.5)


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
