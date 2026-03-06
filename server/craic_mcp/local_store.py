"""Local SQLite knowledge store for CRAIC.

Stores knowledge units in a SQLite database at ~/.craic/local.db.
Auto-creates the database directory and schema on first use.
Implements the context manager protocol for deterministic resource cleanup.
"""

import sqlite3
from pathlib import Path
from types import TracebackType

from .knowledge_unit import KnowledgeUnit
from .scoring import calculate_relevance

DEFAULT_DB_PATH = Path.home() / ".craic" / "local.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_units (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_unit_domains (
    unit_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    FOREIGN KEY (unit_id) REFERENCES knowledge_units(id) ON DELETE CASCADE,
    PRIMARY KEY (unit_id, domain)
);

CREATE INDEX IF NOT EXISTS idx_domains_domain
    ON knowledge_unit_domains(domain);
"""


def _normalise_domains(domains: list[str]) -> list[str]:
    """Lowercase, strip whitespace, drop empties, and deduplicate domain tags."""
    return list(dict.fromkeys(d.strip().lower() for d in domains if d.strip()))


class LocalStore:
    """SQLite-backed local knowledge store.

    Holds a single persistent connection for the lifetime of the instance.
    Use as a context manager or call ``close()`` explicitly.

    Not thread-safe — each thread should create its own instance.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialise the store, creating the database and schema if needed.

        Args:
            db_path: Path to the SQLite database file. Defaults to ~/.craic/local.db.
        """
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._closed = False
        self._conn = self._open_connection()
        self._ensure_schema()

    def _open_connection(self) -> sqlite3.Connection:
        """Open and configure a SQLite connection."""
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _ensure_schema(self) -> None:
        """Create tables and indexes if they do not exist."""
        self._conn.executescript(_SCHEMA_SQL)

    def _check_open(self) -> None:
        """Raise if the store has been closed."""
        if self._closed:
            raise RuntimeError("LocalStore is closed")

    def close(self) -> None:
        """Close the underlying database connection."""
        if self._closed:
            return
        self._closed = True
        self._conn.close()

    def __enter__(self) -> "LocalStore":
        """Enter the context manager."""
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        """Exit the context manager, closing the connection."""
        self.close()

    @property
    def db_path(self) -> Path:
        """Path to the SQLite database file."""
        return self._db_path

    def insert(self, unit: KnowledgeUnit) -> None:
        """Insert a knowledge unit into the store.

        Args:
            unit: The knowledge unit to insert.

        Raises:
            sqlite3.IntegrityError: If a unit with the same ID already exists.
        """
        self._check_open()
        domains = _normalise_domains(unit.domain)
        unit = unit.model_copy(update={"domain": domains})
        data = unit.model_dump_json()
        with self._conn:
            self._conn.execute(
                "INSERT INTO knowledge_units (id, data) VALUES (?, ?)",
                (unit.id, data),
            )
            self._conn.executemany(
                "INSERT INTO knowledge_unit_domains (unit_id, domain) VALUES (?, ?)",
                [(unit.id, d) for d in domains],
            )

    def get(self, unit_id: str) -> KnowledgeUnit | None:
        """Retrieve a knowledge unit by ID.

        Args:
            unit_id: The knowledge unit identifier.

        Returns:
            The knowledge unit, or None if not found.
        """
        self._check_open()
        row = self._conn.execute(
            "SELECT data FROM knowledge_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
        if row is None:
            return None
        return KnowledgeUnit.model_validate_json(row[0])

    def update(self, unit: KnowledgeUnit) -> None:
        """Replace an existing knowledge unit in the store.

        Args:
            unit: The updated knowledge unit.

        Raises:
            KeyError: If no unit with the given ID exists.
        """
        self._check_open()
        domains = _normalise_domains(unit.domain)
        unit = unit.model_copy(update={"domain": domains})
        data = unit.model_dump_json()
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE knowledge_units SET data = ? WHERE id = ?",
                (data, unit.id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Knowledge unit not found: {unit.id}")
            self._conn.execute(
                "DELETE FROM knowledge_unit_domains WHERE unit_id = ?",
                (unit.id,),
            )
            self._conn.executemany(
                "INSERT INTO knowledge_unit_domains (unit_id, domain) VALUES (?, ?)",
                [(unit.id, d) for d in domains],
            )

    def query(
        self,
        domains: list[str],
        *,
        language: str | None = None,
        framework: str | None = None,
        limit: int = 5,
    ) -> list[KnowledgeUnit]:
        """Search for knowledge units by domain tags with relevance ranking.

        Finds units with at least one overlapping domain tag, optionally
        filters by language or framework context, then ranks results by
        relevance * confidence.

        Args:
            domains: Domain tags to search for.
            language: Optional programming language filter.
            framework: Optional framework filter.
            limit: Maximum number of results to return.

        Returns:
            Knowledge units ranked by relevance * confidence, descending.
        """
        self._check_open()
        if not domains:
            return []

        normalised = _normalise_domains(domains)
        if not normalised:
            return []
        # Safe: placeholders is only '?' characters, never user input.
        placeholders = ",".join("?" for _ in normalised)
        sql = f"""
            SELECT ku.data
            FROM knowledge_units ku
            WHERE ku.id IN (
                SELECT DISTINCT unit_id
                FROM knowledge_unit_domains
                WHERE domain IN ({placeholders})
            )
        """
        rows = self._conn.execute(sql, normalised).fetchall()

        # PoC: all filtering and scoring is in-memory after deserialization.
        # For larger stores, push coarse filters into SQL.
        units = [KnowledgeUnit.model_validate_json(row[0]) for row in rows]

        if language:
            units = [u for u in units if language in u.context.languages]
        if framework:
            units = [u for u in units if framework in u.context.frameworks]

        scored = []
        for unit in units:
            relevance = calculate_relevance(
                unit,
                normalised,
                query_language=language,
                query_framework=framework,
            )
            scored.append((relevance * unit.evidence.confidence, unit))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [unit for _, unit in scored[:limit]]
