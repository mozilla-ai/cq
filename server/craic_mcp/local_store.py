"""Local SQLite knowledge store for CRAIC."""

import sqlite3
from pathlib import Path

from .knowledge_unit import KnowledgeUnit
from .scoring import calculate_relevance

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS knowledge_units (
    id   TEXT PRIMARY KEY,
    data TEXT NOT NULL
)
"""


class LocalStore:
    DEFAULT_PATH = Path.home() / ".craic" / "local.db"

    def __init__(self, db_path: Path = DEFAULT_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._init_db()

    def _init_db(self) -> None:
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()

    def insert(self, unit: KnowledgeUnit) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO knowledge_units (id, data) VALUES (?, ?)",
            (unit.id, unit.model_dump_json()),
        )
        self._conn.commit()

    def get(self, id: str) -> KnowledgeUnit | None:
        row = self._conn.execute(
            "SELECT data FROM knowledge_units WHERE id = ?", (id,)
        ).fetchone()
        if row is None:
            return None
        return KnowledgeUnit.model_validate_json(row[0])

    def update(self, unit: KnowledgeUnit) -> None:
        self._conn.execute(
            "UPDATE knowledge_units SET data = ? WHERE id = ?",
            (unit.model_dump_json(), unit.id),
        )
        self._conn.commit()

    def query(
        self,
        domains: list[str],
        language: str | None = None,
        framework: str | None = None,
        limit: int = 5,
    ) -> list[KnowledgeUnit]:
        rows = self._conn.execute("SELECT data FROM knowledge_units").fetchall()
        units = [KnowledgeUnit.model_validate_json(row[0]) for row in rows]
        scored = [
            (calculate_relevance(u, domains, language, framework) * u.evidence.confidence, u)
            for u in units
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [u for _, u in scored[:limit]]
