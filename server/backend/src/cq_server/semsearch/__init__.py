"""Semantic-search helpers backed by sqlite-vec and remote token embeddings.

This module provides optional semantic indexing and retrieval for knowledge units.
Semantic search is enabled only when `TOKEN_EMBEDDING_URL` is configured and the
embedding dependencies are installed.
"""

import logging
import os
import sqlite3
from sqlalchemy.sql.expression import TextClause, text

logger = logging.getLogger(__name__)

_ENABLED = False
_DIM = int(os.environ.get("SEMSEARCH_EMBEDDING_DIM", 768))


_TOKEN_EMBEDDING_URL = os.environ.get("TOKEN_EMBEDDING_URL")
if _TOKEN_EMBEDDING_URL:
    try:
        import sqlite_vec
        import numpy as np
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
        vec_distance_cosine(vec.embedding, :query_embedding) as distance
    FROM knowledge_units_vec vec
    JOIN knowledge_units ku ON ku.id = vec.id
    WHERE ku.status = 'approved'
    ORDER BY distance
    LIMIT :limit
"""

_QUERY_VEC_COMBINED_SQL = """
    SELECT
        ku.data,
        vec_distance_cosine(vec.embedding, :query_embedding) as distance
    FROM knowledge_units ku
    JOIN knowledge_units_vec vec ON ku.id = vec.id
    WHERE ku.status = 'approved'
    AND ku.id IN (
        SELECT DISTINCT unit_id
        FROM knowledge_unit_domains
        WHERE domain IN :domains
    )
    ORDER BY distance LIMIT :limit
"""

_VEC_DELETE_SQL = "DELETE FROM knowledge_units_vec WHERE id = :unit_id"
_VEC_INSERT_SQL = "INSERT INTO knowledge_units_vec (id, embedding) VALUES (:unit_id, :embedding)"


def is_enabled() -> bool:
    """Return whether semantic search dependencies are available."""
    return _ENABLED


def load(conn, _) -> None:
    """Load the sqlite-vec extension into an SQLite connection."""
    if not _ENABLED:
        return
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    ensure_schema(conn)


def ensure_schema(conn) -> None:
    """Create semantic search virtual table if embedding is enabled."""
    if not _ENABLED:
        return
    conn.executescript(_VEC_SCHEMA_SQL.format(dim=_DIM))
