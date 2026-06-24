"""Semantic-search helpers backed by sqlite-vec and remote token embeddings.

This module provides optional semantic indexing and retrieval for knowledge units.
Semantic search is enabled only when `TOKEN_EMBEDDING_URL` is configured and the
embedding dependencies are installed.
"""

import logging
import sqlite3
from typing import Any

from cq.models import KnowledgeUnit
from cq.scoring import calculate_relevance
from sqlalchemy.sql.expression import bindparam
from sqlalchemy.sql.expression import text as text_clause

from ..core.db import Database
from ..repositories._normalize import normalize_domains
from . import (
    _QUERY_VEC_COMBINED_SQL,
    _TOKEN_EMBEDDING_URL,
    _VEC_DELETE_SQL,
    _VEC_INSERT_SQL,
)
from . import is_enabled as semsearch_enabled

logger = logging.getLogger(__name__)


class SemsearchError(RuntimeError):
    """Base error for semantic-search operations."""


class EmbeddingServiceError(SemsearchError):
    """Raised when embedding server communication or payload validation fails."""


if semsearch_enabled():
    import numpy as np
    import numpy.typing as npt
    import sqlite_vec
    from httpx import AsyncClient, HTTPStatusError, RequestError


async def _get_embeddings(wordlist: list[str]) -> "npt.ArrayLike":
    """Fetches and the average embedding vector for the input strings from the embedding service.

    Fetches embedding vectors for the provided list of strings from a remote embedding API and computes
    the average embedding vector across all returned embeddings. The embedding API is expected to
    return a JSON response containing a "results" field, which is a list of objects each containing an
    "embeddings" field with a list of embedding objects. Each embedding object should have an "embedding"
    field containing the embedding vector as a list of floats.

    Parameters:
        wordlist (list[str]): Input strings to send to the embedding API.

    Returns:
        npt.ArrayLike: The averaged embedding vector computed across returned embeddings.

    Raises:
        RuntimeError: If semantic search is not enabled or if the embedding API returns no
            embeddings for the given input.
    """
    if not semsearch_enabled():
        raise RuntimeError(
            "Semantic search is not enabled. Set TOKEN_EMBEDDING_URL and install required packages to enable."
        )
    request_data = {"inputs": wordlist}
    try:
        async with AsyncClient(base_url=_TOKEN_EMBEDDING_URL, timeout=30.0) as client:  # ty: ignore[invalid-argument-type]
            response = await client.post("/predict", json=request_data)
            response.raise_for_status()
    except RequestError as e:
        raise EmbeddingServiceError("Failed to reach embedding API") from e
    except HTTPStatusError as e:
        raise EmbeddingServiceError("Embedding API returned an error status") from e

    try:
        payload = response.json()
    except ValueError as e:
        raise EmbeddingServiceError("Embedding API returned invalid JSON") from e

    if not isinstance(payload, dict):
        raise EmbeddingServiceError("Embedding API response must be a JSON object")

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        raise EmbeddingServiceError(f"Embedding API returned no embeddings for input: {request_data}")

    try:
        embeddings = [embedding.get("embedding") for embedding in results[0]["embeddings"]]
    except (KeyError, TypeError, AttributeError) as e:
        raise EmbeddingServiceError("Embedding API response has unexpected structure") from e

    try:
        return np.average(np.array(embeddings), axis=0)
    except (TypeError, ValueError) as e:
        raise EmbeddingServiceError("Embedding API returned invalid embedding values") from e


def _serialize_embedding(vec: "npt.ArrayLike") -> bytes:
    """Convert an embedding vector to sqlite-vec compatible bytes."""
    arr = np.asarray(vec, dtype=np.float32)
    if hasattr(sqlite_vec, "serialize_float32"):
        return sqlite_vec.serialize_float32(arr)  # ty: ignore[invalid-argument-type]
    return arr.tobytes()


def build_insert_vec_clauses(unit: KnowledgeUnit, serialized: bytes) -> list[tuple[Any, dict[str, Any]]]:
    """Build vector-index insert clauses for a knowledge unit."""
    return [(text_clause(_VEC_INSERT_SQL), {"unit_id": unit.id, "embedding": serialized})]


async def insert_unit(
    db: Database,
    unit: KnowledgeUnit,
    base_clauses: list[tuple[Any, dict[str, Any]]] | None = None,
) -> None:
    """Insert a KnowledgeUnit's embedding into the vector index.

    Builds a single insight text from the unit's insight fields and inserts a serialized embedding
        row for the unit into the database.

    Parameters:
        db (Database): Database instance used to execute the insert statement.
        unit (KnowledgeUnit): Unit whose insight text will be embedded and stored.

    Raises:
        ValueError: If the combined insight text is empty.
    """
    if not semsearch_enabled():
        logger.warning("Attempted to insert embedding while semantic search is disabled; skipping embedding insert")
        return
    text = " ".join([unit.insight.summary, unit.insight.detail, unit.insight.action]).strip()
    if not text:
        raise ValueError("Cannot insert embedding for unit with empty insight text")
    embedding = await _get_embeddings([text])
    serialized = _serialize_embedding(embedding)
    clauses = [*(base_clauses or []), *build_insert_vec_clauses(unit, serialized)]
    await db.run_sync(db.run_clauses_sync, clauses)
    return


def build_update_vec_clauses(unit: KnowledgeUnit, serialized: bytes) -> list[tuple[Any, dict[str, Any]]]:
    """Build vector-index update clauses (delete then insert) for a knowledge unit."""
    return [
        (text_clause(_VEC_DELETE_SQL), {"unit_id": unit.id}),
        (text_clause(_VEC_INSERT_SQL), {"unit_id": unit.id, "embedding": serialized}),
    ]


async def update_unit(
    db: Database,
    unit: KnowledgeUnit,
    base_clauses: list[tuple[Any, dict[str, Any]]] | None = None,
) -> None:
    """Update a KnowledgeUnit's embedding in the vector index.

    Deletes the existing embedding for the unit (if present) and inserts a fresh embedding
        built from the updated unit's insight fields.

    Parameters:
        db (Database): Database instance used to execute the delete and insert statements.
        unit (KnowledgeUnit): Unit whose embedding will be updated.

    Raises:
        ValueError: If the combined insight text is empty (from insert_unit).
    """
    if not semsearch_enabled():
        logger.warning("Attempted to update embedding while semantic search is disabled; skipping embedding update")
        return
    text = " ".join([unit.insight.summary, unit.insight.detail, unit.insight.action]).strip()
    if not text:
        raise ValueError("Cannot insert embedding for unit with empty insight text")
    embedding = await _get_embeddings([text])
    serialized = _serialize_embedding(embedding)
    clauses = [*(base_clauses or []), *build_update_vec_clauses(unit, serialized)]
    await db.run_sync(db.run_clauses_sync, clauses)
    return


async def combined_query(
    db: Database,
    domains: list[str],
    languages: list[str] | None,
    frameworks: list[str] | None,
    pattern: str,
    *,
    limit: int = 5,
    base_clauses: list[tuple[Any, dict[str, Any]]] | None = None,
) -> list[Any]:
    """Perform a combined domain-filtered vector search and return ranked KnowledgeUnit results.

    Performs a vector search constrained to the provided domains, re-ranks results by a combination
        of calculated relevance and vector distance (weighted), applies each unit's evidence confidence,
        and returns the top results ordered by combined score (highest first).

    Parameters:
        db (Database): Database instance used to execute the combined query.
        domains (list[str]): Domains to filter and to use for computing the query embedding; must be non-empty.
        languages (list[str] | None): Optional list of languages to guide relevance calculation.
        frameworks (list[str] | None): Optional list of frameworks to guide relevance calculation.
        pattern (str): Pattern used to influence relevance scoring.
        limit (int, optional): Maximum number of results to return; must be greater than zero. Defaults to 5.

    Returns:
        list[Any]: List of matching KnowledgeUnit objects ordered by combined score (highest first), limited to `limit`.

    Raises:
        RuntimeError: If semantic search is not enabled, or if a database/general error occurs during the query.
        ValueError: If `limit` is not a positive integer.
    """
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
    query_clauses = base_clauses or []
    try:
        vec_emb_search = await _get_embeddings(domains)
        search_embedding = _serialize_embedding(vec_emb_search)
        args = {"query_embedding": search_embedding, "limit": limit, "domains": normalized}
        clause = text_clause(_QUERY_VEC_COMBINED_SQL).bindparams(bindparam("domains", expanding=True))
        if isinstance(db, Database):
            vec_rows = await db.run_sync(
                db.run_clauses_sync,
                [*query_clauses, (clause, args)],
                fetch=True,
            )
    except sqlite3.OperationalError as e:
        logger.warning("Database error when performing combined query", exc_info=True)
        raise RuntimeError("Database error when performing combined query") from e
    except Exception as e:
        logger.warning("General error when performing combined query", exc_info=True)
        raise RuntimeError("General error when performing combined query") from e
    units = [(KnowledgeUnit.model_validate_json(row), distance) for row, distance in vec_rows]
    total_distance = sum(distance for _, distance in units)

    def combine(relevance, distance) -> float:
        """Combine a relevance score and a distance into a single weighted score.

        Parameters:
            relevance (float): Base relevance value to weight.
            distance (float): Non-negative distance value; it is normalized by the module-level
                `total_distance` (treated as 0 if `total_distance` <= 0) before weighting.

        Returns:
            float: Combined score computed as 0.8 * relevance + 0.2 * (normalized distance),
                where normalized distance is `distance / total_distance` or 0 when `total_distance` is 0.
        """
        relevance_weight = 0.8
        distance_weight = 0.2
        normalized_distance = distance / total_distance if total_distance > 0 else 0
        result = relevance * relevance_weight + normalized_distance * distance_weight
        return result

    scored = [
        (
            combine(
                calculate_relevance(
                    u,
                    normalized,
                    query_languages=languages,
                    query_frameworks=frameworks,
                    query_pattern=pattern,
                ),
                distance,
            )
            * u.evidence.confidence,
            u.id,
            u,
        )
        for u, distance in units
    ]
    # Match RemoteStore tie-break: score desc, id desc on tie.
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [u for _, _, u in scored[:limit]]
