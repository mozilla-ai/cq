"""Semantic-search helpers backed by sqlite-vec and remote token embeddings.

This module provides optional semantic indexing and retrieval for knowledge units.
Semantic search is enabled only when `TOKEN_EMBEDDING_URL` is configured and the
embedding dependencies are installed.
"""

import logging
import math
from pydoc import text
import sqlite3
from typing import Any

from cq.models import KnowledgeUnit
from cq.scoring import calculate_relevance
from ..repositories._normalize import normalize_domains
from . import is_enabled as semsearch_enabled, _TOKEN_EMBEDDING_URL, _DIM, _VEC_DELETE_SQL, _VEC_INSERT_SQL, _VEC_SEARCH_SQL, _QUERY_VEC_COMBINED_SQL
from sqlalchemy.sql.expression import text as text_clause, bindparam
from sqlalchemy.engine.base import Connection

logger = logging.getLogger(__name__)

if semsearch_enabled():
    import sqlite_vec
    import numpy as np
    import numpy.typing as npt
    from httpx import AsyncClient

async def _get_embeddings(wordlist: list[str]) -> "npt.ArrayLike":
    """Get embeddings for a list of words using the embedding API."""
    if not semsearch_enabled():
        raise RuntimeError(
            "Semantic search is not enabled. Set TOKEN_EMBEDDING_URL and install required packages to enable."
        )
    async with AsyncClient(base_url=_TOKEN_EMBEDDING_URL) as client:  # ty: ignore[invalid-argument-type]
        request_data = {"inputs": wordlist}
        response = await client.post("/predict", json=request_data)
        response.raise_for_status()
        results = response.json().get("results")
        if not results:
            raise RuntimeError(f"Embedding API returned no embeddings for input: {request_data}")
        return np.average(np.array([embedding.get("embedding") for embedding in results[0]["embeddings"]]), axis=0)


def _serialize_embedding(vec: "npt.ArrayLike") -> bytes:
    """Convert an embedding vector to sqlite-vec compatible bytes."""
    arr = np.asarray(vec, dtype=np.float32)
    if hasattr(sqlite_vec, "serialize_float32"):
        return sqlite_vec.serialize_float32(arr)  # ty: ignore[invalid-argument-type]
    return arr.tobytes()


# check type of sqlalchemy conns
async def upsert_unit(conn, unit: KnowledgeUnit) -> None:
    """Update a knowledge unit embedding row."""
    if not semsearch_enabled():
        return
    text = " ".join([unit.insight.summary, unit.insight.detail, unit.insight.action]).strip()
    if not text:
        return
    embedding = await _get_embeddings([text])
    serialized = _serialize_embedding(embedding)
    conn.execute(text_clause(_VEC_DELETE_SQL), {"unit_id": unit.id})
    conn.execute(text_clause(_VEC_INSERT_SQL), {"unit_id": unit.id, "embedding": serialized})


async def insert_unit(conn, unit: KnowledgeUnit) -> None:
    """Insert a knowledge unit embedding row."""
    if not semsearch_enabled():
        logging.warning("Attempted to insert embedding while semantic search is disabled; skipping embedding insert")
        return
    text = " ".join([unit.insight.summary, unit.insight.detail, unit.insight.action]).strip()
    if not text:
        raise ValueError("Cannot insert embedding for unit with empty insight text")
    embedding = await _get_embeddings([text])
    serialized = _serialize_embedding(embedding)
    res = conn.execute(text_clause(_VEC_INSERT_SQL), {"unit_id": unit.id, "embedding": serialized})


# check type of sqlalchemy conns
async def query(conn,
                domains: list[str],
                languages: list[str] | None,
                frameworks: list[str] | None,
                pattern: str,
                *,
                limit: int = 5,
            ) -> list[KnowledgeUnit]:
    """Semantic search implementation."""
    if not semsearch_enabled():
        raise RuntimeError(
            "Semantic search is not enabled. Set TOKEN_EMBEDDING_URL and install required packages to enable."
        )
    if not domains:
        return []
    if limit <= 0:
        return []
    normalized = normalize_domains(domains)
    if not normalized:
        return []
    try:
        vec_emb_search = await _get_embeddings(normalized)
        search_embedding = _serialize_embedding(vec_emb_search)
        vec_rows = conn.execute(text_clause(_VEC_SEARCH_SQL), {"query_embedding": search_embedding, "limit": limit}).fetchall()
        logger.info(f"Vector search returned {len(vec_rows)} rows for domains {normalized} with limit {limit}")
    except sqlite3.OperationalError as e:
        raise RuntimeError("Database error when performing base query") from e
    units= [KnowledgeUnit.model_validate_json(row[0]) for row in vec_rows]
    scored = [
        (
            calculate_relevance(
                u,
                normalized,
                query_languages=languages,
                query_frameworks=frameworks,
                query_pattern=pattern,
            )
            * u.evidence.confidence,
            u.id,
            u,
        )
        for u in units
    ]
    # Match RemoteStore tie-break: score desc, id desc on tie.
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [u for _, _, u in scored[:limit]]


async def combined_query(conn: Connection,
                domains: list[str],
                languages: list[str] | None,
                frameworks: list[str] | None,
                pattern: str,
                *,
                limit: int = 5,) -> list[Any]:
    """Generate SQL for a combined domain filter + vector search query."""
    if not semsearch_enabled():
        raise RuntimeError(
            "Semantic search is not enabled. Set TOKEN_EMBEDDING_URL and install required packages to enable."
        )
    if not domains:
        return []
    if limit <= 0:
        raise ValueError("limit must be positive")
    normalized = normalize_domains(domains)
    if not normalized:
        return []
    try:
        vec_emb_search = await _get_embeddings(domains)
        search_embedding = _serialize_embedding(vec_emb_search)
        args = {"query_embedding": search_embedding, "limit": limit, "domains": normalized}
        clause = text_clause(_QUERY_VEC_COMBINED_SQL).bindparams(bindparam("domains", expanding=True))
        vec_rows = conn.execute(clause, args).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning("Database error when performing combined query", exc_info=True)
        raise RuntimeError("Database error when performing combined query") from e
    except Exception as e:
        logger.warning("General error when performing combined query", exc_info=True)
        raise RuntimeError("General error when performing combined query") from e
    units = [(KnowledgeUnit.model_validate_json(row), distance) for row, distance in vec_rows]
    total_distance = sum(distance for _, distance in units)
    def combine(relevance, distance) -> float:
        """Combine relevance and distance into a single score."""
        # Simple example: partially weighted over normalized distance
        relevance_weight = 0.8
        distance_weight = 0.2
        normalized_distance = distance / total_distance if total_distance > 0 else 0
        result = relevance * relevance_weight + normalized_distance * distance_weight
        return result

    # Re arrange rows according to distance
    scored = [
        (
            combine(calculate_relevance(
                u,
                normalized,
                query_languages=languages,
                query_frameworks=frameworks,
                query_pattern=pattern,
            ), distance)
            * u.evidence.confidence,
            u.id,
            u,
        )
        for u, distance in units
    ]
    # Match RemoteStore tie-break: score desc, id desc on tie.
    # Re arrange rows according to distance
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [u for _, _, u in scored[:limit]]



def build_field_logits(
    row_data_by_id: dict[str, tuple[Any, ...]],
    *,
    invert: bool = True,
) -> dict[int, dict[Any, float]]:
    """Build logit-normalized scores for each additional field across all rows.

    When ``invert`` is True (the default), lower field values — e.g. cosine
    distances — receive higher logits.
    """
    field_logits: dict[int, dict[Any, float]] = {}
    if not row_data_by_id:
        return field_logits

    max_fields = max(len(data) for data in row_data_by_id.values())
    for field_idx in range(max_fields):
        values: list[float] = []
        for data in row_data_by_id.values():
            if field_idx < len(data) and isinstance(data[field_idx], (int, float)):
                values.append(float(data[field_idx]))
        if not values:
            continue

        min_val = min(values)
        max_val = max(values)
        if min_val == max_val:
            field_logits[field_idx] = {v: 0.0 for v in values}
            continue

        mean_val = sum(values) / len(values)
        field_logits[field_idx] = {}
        for v in values:
            ratio = (v / mean_val) if mean_val != 0 else 1.0
            logit = -math.log(ratio) if invert else math.log(ratio)
            field_logits[field_idx][v] = logit

    return field_logits


def compute_combined_relevance(
    base_relevance: float,
    row_data: tuple[Any, ...],
    field_logits: dict[int, dict[Any, float]],
) -> float:
    """Multiply base relevance by ``(1 + logit)`` for each per-row field.

    Keeps the combined score positive while letting low-distance rows
    boost their score and high-distance rows diminish it.
    """
    combined = base_relevance
    for field_idx, logit_map in field_logits.items():
        if field_idx < len(row_data):
            combined *= 1.0 + logit_map.get(row_data[field_idx], 0.0)
    return combined
