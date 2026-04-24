import logging
import os
import sqlite3
import numpy as np

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


_VEC_SCHEMA_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_units_vec
    USING vec0(
        id TEXT PRIMARY KEY,
        embedding float[{dim}]
    );
"""

_VEC_SEARCH_SQL = """
    SELECT ku.data
    FROM knowledge_units_vec vec
    JOIN knowledge_units ku ON ku.id = vec.id
    WHERE ku.status = 'approved'
            AND vec.embedding MATCH ?
            AND k = ?
        ORDER BY vec.distance
"""

_VEC_DELETE_SQL = "DELETE FROM knowledge_units_vec WHERE id = ?"
_VEC_INSERT_SQL = "INSERT INTO knowledge_units_vec (id, embedding) VALUES (?, ?)"


async def _get_embeddings(wordlist: list[str]) -> list[np.array]:
    """Get embeddings for a list of words using the embedding API."""
    if not _ENABLED:
        raise RuntimeError("Semantic search is not enabled. Set TOKEN_EMBEDDING_URL and install required packages to enable.")
    async with AsyncClient(base_url=_TOKEN_EMBEDDING_URL) as client:
        request_data = {"inputs": wordlist}
        response = await client.post("/predict", json=request_data)
        response.raise_for_status()
        results = response.json().get("results")
        if not results:
            raise RuntimeError(f"Embedding API returned no embeddings for input: {request_data}")
        return [np.average(np.array([embedding.get("embedding") for embedding in embeddings["embeddings"]]), axis=0) for embeddings in results]


def is_enabled() -> bool:
    """Return whether semantic search dependencies are available."""
    return _ENABLED


def _serialize_embedding(vec: np.ndarray) -> bytes:
    arr = np.asarray(vec, dtype=np.float32)
    if hasattr(sqlite_vec, "serialize_float32"):
        return sqlite_vec.serialize_float32(arr)
    return arr.tobytes()

def load(conn: sqlite3.Connection) -> None:
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
    embedding = (await _get_embeddings([text]))[0]
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
    search_embedding = _serialize_embedding(vec_emb_search[0])
    try:
        vec_rows = conn.execute(_VEC_SEARCH_SQL, (search_embedding, limit)).fetchall()
    except sqlite3.OperationalError:
        vec_rows = []
    return [KnowledgeUnit.model_validate_json(row[0]) for row in vec_rows]
