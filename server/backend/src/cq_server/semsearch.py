"""Semantic-search helpers backed by sqlite-vec and remote token embeddings.

This module provides optional semantic indexing and retrieval for knowledge units.
Semantic search is enabled only when `TOKEN_EMBEDDING_URL` is configured and the
embedding dependencies are installed.
"""

import logging
import os
import sqlite3
from typing import Any

import numpy as np
import numpy.typing as npt
from cq.models import KnowledgeUnit

logger = logging.getLogger(__name__)

_ENABLED = False
_DIM = int(os.environ.get("SEMSEARCH_EMBEDDING_DIM", 768))


_TOKEN_EMBEDDING_URL = os.environ.get("TOKEN_EMBEDDING_URL")
if _TOKEN_EMBEDDING_URL:
    try:
        import sqlite_vec
        from httpx import AsyncClient

        _ENABLED = True

        logger.info(f"Token embedding enabled using encoderfile endpoint at {_TOKEN_EMBEDDING_URL}")
    except ImportError:
        logger.warning(
            "TOKEN_EMBEDDING_URL is set but required packages are not installed; "
            "semantic search will be unavailable. To enable, install cq with "
            "the 'embedding' extra: pip install cq-sdk[embedding]",
            exc_info=True,
        )


# We have avoided using vec0 table since we won't be doing knn-style
# search, but rather filtering by domain and then ranking by distance.
# The syntax for a vec0 table would be:
# CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_units_vec
#     USING vec0(
#         id TEXT PRIMARY KEY,
#         embedding float[{dim}]
#     );
_VEC_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_units_vec(
    id TEXT PRIMARY KEY,
    embedding float[{dim}]
    check(
      typeof(embedding) == 'blob'
      and vec_length(embedding) == {dim}
    )
);
"""

_VEC_SEARCH_SQL = """
    SELECT
        ku.data,
        vec_distance_cosine(vec.embedding, ?) as distance
    FROM knowledge_units_vec vec
    JOIN knowledge_units ku ON ku.id = vec.id
    WHERE ku.status = 'approved'
    ORDER BY distance
    LIMIT ?
"""

_QUERY_VEC_COMBINED_SQL = """
    SELECT
        ku.data,
        vec_distance_cosine(vec.embedding, ?) as distance
    FROM knowledge_units ku
    JOIN knowledge_units_vec vec ON ku.id = vec.id
    WHERE ku.status = 'approved'
    AND ku.id IN (
        SELECT DISTINCT unit_id
        FROM knowledge_unit_domains
        WHERE domain IN ({placeholders})
    )
"""

_VEC_DELETE_SQL = "DELETE FROM knowledge_units_vec WHERE id = ?"
_VEC_INSERT_SQL = "INSERT INTO knowledge_units_vec (id, embedding) VALUES (?, ?)"


async def _get_embeddings(wordlist: list[str]) -> npt.ArrayLike:
    """Get embeddings for a list of words using the embedding API."""
    if not _ENABLED:
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


def is_enabled() -> bool:
    """Return whether semantic search dependencies are available."""
    return _ENABLED


def _serialize_embedding(vec: npt.ArrayLike) -> bytes:
    """Convert an embedding vector to sqlite-vec compatible bytes."""
    arr = np.asarray(vec, dtype=np.float32)
    if hasattr(sqlite_vec, "serialize_float32"):
        return sqlite_vec.serialize_float32(arr)  # ty: ignore[invalid-argument-type]
    return arr.tobytes()


def load(conn: sqlite3.Connection) -> None:
    """Load the sqlite-vec extension into an SQLite connection."""
    if not _ENABLED:
        return
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create semantic search virtual table if embedding is enabled."""
    if not _ENABLED:
        return
    conn.executescript(_VEC_SCHEMA_SQL.format(dim=_DIM))


async def upsert_unit(conn: sqlite3.Connection, unit: KnowledgeUnit) -> None:
    """Insert or update a knowledge unit embedding row."""
    if not _ENABLED:
        return
    text = " ".join([unit.insight.summary, unit.insight.detail, unit.insight.action]).strip()
    if not text:
        return
    embedding = await _get_embeddings([text])
    serialized = _serialize_embedding(embedding)
    conn.execute(_VEC_DELETE_SQL, (unit.id,))
    conn.execute(_VEC_INSERT_SQL, (unit.id, serialized))


async def query(conn: sqlite3.Connection, domains: list[str], *, limit: int = 5) -> list[KnowledgeUnit]:
    """Semantic search implementation."""
    if not _ENABLED:
        return []
    if not domains:
        return []
    if limit <= 0:
        return []
    vec_emb_search = await _get_embeddings(domains)
    search_embedding = _serialize_embedding(vec_emb_search)
    try:
        vec_rows = conn.execute(_VEC_SEARCH_SQL, (search_embedding, limit)).fetchall()
    except sqlite3.OperationalError:
        vec_rows = []
    return [KnowledgeUnit.model_validate_json(row[0]) for row in vec_rows]


async def combined_query(conn: sqlite3.Connection, domains: list[str], placeholders: str) -> list[Any]:
    """Generate SQL for a combined domain filter + vector search query."""
    if not _ENABLED:
        return []
    if not domains:
        return []
    vec_emb_search = await _get_embeddings(domains)
    search_embedding = _serialize_embedding(vec_emb_search)
    try:
        args = [search_embedding] + domains
        vec_rows = conn.execute(_QUERY_VEC_COMBINED_SQL.format(placeholders=placeholders), args).fetchall()
    except sqlite3.OperationalError:
        logger.warning(f"args: {vec_emb_search.shape}")  # ty: ignore[unresolved-attribute]
        logger.warning(f"query: {_QUERY_VEC_COMBINED_SQL.format(placeholders=placeholders)}")
        logger.warning("Combined query failed, falling back to domain-only search", exc_info=True)
        vec_rows = []
    return vec_rows
