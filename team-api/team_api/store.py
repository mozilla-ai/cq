"""SQLite-backed team knowledge store.

Stores knowledge units in a SQLite database for team-level sharing.
Auto-creates the database directory and schema on first use.
Implements the context manager protocol for deterministic resource cleanup.
"""

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

from .knowledge_unit import KnowledgeUnit
from .scoring import calculate_relevance
from .tables import ensure_review_columns, ensure_users_table

DEFAULT_DB_PATH = Path("/data/team.db")

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


def normalise_domains(domains: list[str]) -> list[str]:
    """Lowercase, strip whitespace, drop empties, and deduplicate domain tags."""
    return list(dict.fromkeys(d.strip().lower() for d in domains if d.strip()))


class TeamStore:
    """SQLite-backed team knowledge store.

    Holds a single persistent connection for the lifetime of the instance.
    Use as a context manager or call ``close()`` explicitly.

    Thread-safe: all connection access is serialized via an internal lock.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialise the store, creating the database and schema if needed.

        Args:
            db_path: Path to the SQLite database file. Defaults to /data/team.db.
        """
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._closed = False
        self._lock = threading.Lock()
        self._conn = self._open_connection()
        self._ensure_schema()

    def _open_connection(self) -> sqlite3.Connection:
        """Open and configure a SQLite connection."""
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _ensure_schema(self) -> None:
        """Create tables and indexes if they do not exist."""
        self._conn.executescript(_SCHEMA_SQL)
        ensure_review_columns(self._conn)
        ensure_users_table(self._conn)

    def _check_open(self) -> None:
        """Raise if the store has been closed."""
        if self._closed:
            raise RuntimeError("TeamStore is closed")

    def close(self) -> None:
        """Close the underlying database connection."""
        if self._closed:
            return
        self._closed = True
        self._conn.close()

    def __enter__(self) -> "TeamStore":
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
            ValueError: If domain normalisation results in no valid domains.
        """
        self._check_open()
        domains = normalise_domains(unit.domain)
        if not domains:
            raise ValueError("At least one non-empty domain is required")
        unit = unit.model_copy(update={"domain": domains})
        data = unit.model_dump_json()
        created_at = (
            unit.evidence.first_observed.isoformat() if unit.evidence.first_observed else datetime.now(UTC).isoformat()
        )
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO knowledge_units (id, data, created_at) VALUES (?, ?, ?)",
                (unit.id, data, created_at),
            )
            self._conn.executemany(
                "INSERT INTO knowledge_unit_domains (unit_id, domain) VALUES (?, ?)",
                [(unit.id, d) for d in domains],
            )

    def get(self, unit_id: str) -> KnowledgeUnit | None:
        """Retrieve an approved knowledge unit by ID.

        Agent-facing: only returns KUs that have passed human review.
        For internal access regardless of status, use get_any().

        Args:
            unit_id: The knowledge unit identifier.

        Returns:
            The knowledge unit, or None if not found or not approved.
        """
        self._check_open()
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM knowledge_units WHERE id = ? AND status = 'approved'",
                (unit_id,),
            ).fetchone()
        if row is None:
            return None
        return KnowledgeUnit.model_validate_json(row[0])

    def get_any(self, unit_id: str) -> KnowledgeUnit | None:
        """Retrieve a knowledge unit by ID regardless of review status.

        Internal use only — review endpoints and activity feed.

        Args:
            unit_id: The knowledge unit identifier.

        Returns:
            The knowledge unit, or None if not found.
        """
        self._check_open()
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM knowledge_units WHERE id = ?",
                (unit_id,),
            ).fetchone()
        if row is None:
            return None
        return KnowledgeUnit.model_validate_json(row[0])

    def get_review_status(self, unit_id: str) -> dict[str, str | None] | None:
        """Return review metadata for a knowledge unit.

        Args:
            unit_id: The knowledge unit identifier.

        Returns:
            A dict with status, reviewed_by, and reviewed_at keys, or None
            if the unit does not exist.
        """
        self._check_open()
        with self._lock:
            row = self._conn.execute(
                "SELECT status, reviewed_by, reviewed_at FROM knowledge_units WHERE id = ?",
                (unit_id,),
            ).fetchone()
        if row is None:
            return None
        return {"status": row[0], "reviewed_by": row[1], "reviewed_at": row[2]}

    def set_review_status(self, unit_id: str, status: str, reviewed_by: str) -> None:
        """Update the review status of a knowledge unit.

        Args:
            unit_id: The knowledge unit identifier.
            status: The new review status (e.g. "approved", "rejected").
            reviewed_by: Username of the reviewer.

        Raises:
            KeyError: If no unit with the given ID exists.
        """
        self._check_open()
        now = datetime.now(UTC).isoformat()
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE knowledge_units SET status = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?",
                (status, reviewed_by, now, unit_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Knowledge unit not found: {unit_id}")

    def update(self, unit: KnowledgeUnit) -> None:
        """Replace an existing knowledge unit in the store.

        Args:
            unit: The updated knowledge unit.

        Raises:
            KeyError: If no unit with the given ID exists.
            ValueError: If domain normalisation results in no valid domains.
        """
        self._check_open()
        domains = normalise_domains(unit.domain)
        if not domains:
            raise ValueError("At least one non-empty domain is required")
        unit = unit.model_copy(update={"domain": domains})
        data = unit.model_dump_json()
        with self._lock, self._conn:
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

        Args:
            domains: Domain tags to search for.
            language: Optional programming language filter.
            framework: Optional framework filter.
            limit: Maximum number of results to return. Must be positive.

        Returns:
            Knowledge units ranked by relevance * confidence, descending.

        Raises:
            ValueError: If limit is not positive.
        """
        self._check_open()
        if limit <= 0:
            raise ValueError("limit must be positive")
        if not domains:
            return []

        normalised = normalise_domains(domains)
        if not normalised:
            return []
        # Safe: placeholders is only '?' characters, never user input.
        placeholders = ",".join("?" for _ in normalised)
        sql = f"""
            SELECT ku.data
            FROM knowledge_units ku
            WHERE ku.status = 'approved'
            AND ku.id IN (
                SELECT DISTINCT unit_id
                FROM knowledge_unit_domains
                WHERE domain IN ({placeholders})
            )
        """
        with self._lock:
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

    def count(self) -> int:
        """Return the total number of knowledge units in the store."""
        self._check_open()
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM knowledge_units").fetchone()
        return row[0]

    def domain_counts(self) -> dict[str, int]:
        """Return the count of knowledge units per domain tag."""
        self._check_open()
        with self._lock:
            rows = self._conn.execute(
                "SELECT domain, COUNT(*) FROM knowledge_unit_domains GROUP BY domain ORDER BY COUNT(*) DESC"
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def pending_queue(self, *, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        """Return pending KUs with review metadata, oldest first.

        Args:
            limit: Maximum number of results to return.
            offset: Number of results to skip.

        Returns:
            List of dicts with knowledge_unit, status, reviewed_by,
            and reviewed_at keys.
        """
        self._check_open()
        with self._lock:
            rows = self._conn.execute(
                "SELECT data, status, reviewed_by, reviewed_at "
                "FROM knowledge_units WHERE status = 'pending' "
                "ORDER BY rowid ASC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [
            {
                "knowledge_unit": KnowledgeUnit.model_validate_json(row[0]),
                "status": row[1],
                "reviewed_by": row[2],
                "reviewed_at": row[3],
            }
            for row in rows
        ]

    def pending_count(self) -> int:
        """Return the number of pending KUs."""
        self._check_open()
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM knowledge_units WHERE status = 'pending'").fetchone()
        return row[0]

    def counts_by_status(self) -> dict[str, int]:
        """Return KU counts grouped by review status."""
        self._check_open()
        with self._lock:
            rows = self._conn.execute("SELECT status, COUNT(*) FROM knowledge_units GROUP BY status").fetchall()
        return {row[0]: row[1] for row in rows}

    def daily_counts(self, *, days: int = 30) -> list[dict[str, Any]]:
        """Return daily proposal counts for the last N days.

        Args:
            days: Number of days to look back.

        Returns:
            List of dicts with date and proposed count, ordered ascending.
        """
        self._check_open()
        with self._lock:
            rows = self._conn.execute(
                "SELECT date(created_at) as day, COUNT(*) as proposed "
                "FROM knowledge_units "
                "WHERE created_at >= date('now', ? || ' days') "
                "GROUP BY day ORDER BY day ASC",
                (f"-{days}",),
            ).fetchall()
        return [{"date": row[0], "proposed": row[1]} for row in rows]
