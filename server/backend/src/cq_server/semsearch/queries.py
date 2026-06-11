"""Semantic-search helpers backed by sqlite-vec and remote token embeddings.

This module provides optional semantic indexing and retrieval for knowledge units.
Semantic search is enabled only when `TOKEN_EMBEDDING_URL` is configured and the
embedding dependencies are installed.
"""

import logging
import math
import sqlite3
from typing import Any

from cq.models import KnowledgeUnit
from cq.scoring import calculate_relevance
from sqlalchemy.engine.base import Connection
from sqlalchemy.sql.expression import bindparam
from sqlalchemy.sql.expression import text as text_clause

from ..repositories._normalize import normalize_domains
from . import _QUERY_VEC_COMBINED_SQL, _TOKEN_EMBEDDING_URL, _VEC_DELETE_SQL, _VEC_INSERT_SQL, _VEC_SEARCH_SQL
from . import is_enabled as semsearch_enabled

logger = logging.getLogger(__name__)

if semsearch_enabled():
    import numpy as np
    import numpy.typing as npt
    import sqlite_vec
    from httpx import AsyncClient


async def _get_embeddings(wordlist: list[str]) -> "npt.ArrayLike":
    """
    Fetches and returns the average embedding vector for the provided input strings from the configured embedding service.
    
    Parameters:
        wordlist (list[str]): Input strings to send to the embedding API.
    
    Returns:
        npt.ArrayLike: The averaged embedding vector computed across returned embeddings.
    
    Raises:
        RuntimeError: If semantic search is not enabled or if the embedding API returns no embeddings for the given input.
    """
    if not semsearch_enabled():
        raise RuntimeError(
            "Semantic search is not enabled. Set TOKEN_EMBEDDING_URL and install required packages to enable."
        )
    async with AsyncClient(base_url=_TOKEN_EMBEDDING_URL, timeout=30.0) as client:  # ty: ignore[invalid-argument-type]
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


async def upsert_unit(conn: Connection, unit: KnowledgeUnit) -> None:
    """
    Update the stored vector embedding for a KnowledgeUnit.
    
    If semantic search is disabled or the combined insight text (summary, detail, action) is empty, this function does nothing. Otherwise it deletes any existing vector row for the unit and inserts a new row containing the serialized embedding derived from the unit's insight text.
    """
    if not semsearch_enabled():
        return
    text = " ".join([unit.insight.summary, unit.insight.detail, unit.insight.action]).strip()
    if not text:
        return
    embedding = await _get_embeddings([text])
    serialized = _serialize_embedding(embedding)
    conn.execute(text_clause(_VEC_DELETE_SQL), {"unit_id": unit.id})
    conn.execute(text_clause(_VEC_INSERT_SQL), {"unit_id": unit.id, "embedding": serialized})


async def insert_unit(conn: Connection, unit: KnowledgeUnit) -> None:
    """
    Insert a KnowledgeUnit's embedding into the vector index.
    
    Builds a single insight text from the unit's insight fields and inserts a serialized embedding row for the unit into the database.
    
    Parameters:
    	conn (Connection): Database connection used to execute the insert statement.
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
    conn.execute(text_clause(_VEC_INSERT_SQL), {"unit_id": unit.id, "embedding": serialized})


# check type of sqlalchemy conns
async def query(
    conn: Connection,
    domains: list[str],
    languages: list[str] | None,
    frameworks: list[str] | None,
    pattern: str,
    *,
    limit: int = 5,
) -> list[KnowledgeUnit]:
    """
    Perform a semantic vector search over KnowledgeUnit entries for the given domains and query constraints.
    
    Normalizes `domains` before searching and returns early if domains are empty, normalization yields no domains, or `limit` is not positive. Results are ranked by calculated relevance (using `languages`, `frameworks`, and `pattern` as filters) multiplied by each unit's `evidence.confidence`; ties are broken by unit id in descending order.
    
    Parameters:
        conn (Connection): Database connection used to execute the vector search.
        domains (list[str]): Domain strings to search for; they will be normalized prior to querying.
        languages (list[str] | None): Optional language filter passed to relevance calculation.
        frameworks (list[str] | None): Optional framework filter passed to relevance calculation.
        pattern (str): Pattern string passed to relevance calculation (e.g., code or text pattern to match).
        limit (int, optional): Maximum number of results to return. Defaults to 5.
    
    Returns:
        list[KnowledgeUnit]: Top matching KnowledgeUnit objects ordered by score (relevance × evidence.confidence), limited to `limit`.
    
    Raises:
        RuntimeError: If semantic search is not enabled or if a database error occurs while performing the base query.
    """
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
        vec_rows = conn.execute(
            text_clause(_VEC_SEARCH_SQL), {"query_embedding": search_embedding, "limit": limit}
        ).fetchall()
        logger.info(f"Vector search returned {len(vec_rows)} rows for domains {normalized} with limit {limit}")
    except sqlite3.OperationalError as e:
        raise RuntimeError("Database error when performing base query") from e
    units = [KnowledgeUnit.model_validate_json(row[0]) for row in vec_rows]
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


async def combined_query(
    conn: Connection,
    domains: list[str],
    languages: list[str] | None,
    frameworks: list[str] | None,
    pattern: str,
    *,
    limit: int = 5,
) -> list[Any]:
    """
    Perform a combined domain-filtered vector search and return ranked KnowledgeUnit results.
    
    Performs a vector search constrained to the provided domains, re-ranks results by a combination of calculated relevance and vector distance (weighted), applies each unit's evidence confidence, and returns the top results ordered by combined score (highest first).
    
    Parameters:
        conn (Connection): SQLite connection used to execute the combined query.
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
        """
        Combine a relevance score and a distance into a single weighted score.
        
        Parameters:
            relevance (float): Base relevance value to weight.
            distance (float): Non-negative distance value; it is normalized by the module-level `total_distance` (treated as 0 if `total_distance` <= 0) before weighting.
        
        Returns:
            float: Combined score computed as 0.8 * relevance + 0.2 * (normalized distance), where normalized distance is `distance / total_distance` or 0 when `total_distance` is 0.
        """
        # Simple example: partially weighted over normalized distance
        relevance_weight = 0.8
        distance_weight = 0.2
        normalized_distance = distance / total_distance if total_distance > 0 else 0
        result = relevance * relevance_weight + normalized_distance * distance_weight
        return result

    # Re arrange rows according to distance
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
    # Re arrange rows according to distance
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [u for _, _, u in scored[:limit]]


def build_field_logits(
    row_data_by_id: dict[str, tuple[Any, ...]],
    *,
    invert: bool = True,
) -> dict[int, dict[Any, float]]:
    """
    Compute per-field logit scores from numeric column values across multiple rows.
    
    For each field index present in the input rows, collects numeric values (int/float) and maps each observed value to a logit computed from its ratio to the field mean. If all values for a field are equal, every observed value maps to 0.0. When `invert` is True (default), smaller values produce larger (more positive) logits; when False, larger values produce larger logits.
    
    Parameters:
        row_data_by_id (dict[str, tuple[Any, ...]]): Mapping of row id to a tuple of field values. Non-numeric values are ignored for a field.
        invert (bool, optional): If True, invert the sign of the logit so lower numeric values yield higher scores. Defaults to True.
    
    Returns:
        dict[int, dict[Any, float]]: A mapping from field index to a map of observed numeric values for that field to their logit score.
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
