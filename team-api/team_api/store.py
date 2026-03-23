"""SQLite-backed team knowledge store.

Stores knowledge units in a SQLite database for team-level sharing.
Auto-creates the database directory and schema on first use.
Implements the context manager protocol for deterministic resource cleanup.
"""

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
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
            unit.evidence.first_observed.isoformat()
            if unit.evidence.first_observed
            else datetime.now(UTC).isoformat()
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
            language: Optional language ranking signal. Matching KUs
                rank higher but non-matching KUs are still returned.
            framework: Optional framework ranking signal. Matching KUs
                rank higher but non-matching KUs are still returned.
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

        scored = []
        for unit in units:
            relevance = calculate_relevance(
                unit,
                normalised,
                query_language=language,
                query_framework=framework,
            )
            scored.append((relevance * unit.evidence.confidence, unit))

        scored.sort(key=lambda pair: (pair[0], pair[1].id), reverse=True)
        return [unit for _, unit in scored[:limit]]

    def count(self) -> int:
        """Return the total number of knowledge units in the store."""
        self._check_open()
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM knowledge_units").fetchone()
        return row[0]

    def domain_counts(self) -> dict[str, int]:
        """Return the count of approved knowledge units per domain tag."""
        self._check_open()
        with self._lock:
            rows = self._conn.execute(
                "SELECT d.domain, COUNT(*) "
                "FROM knowledge_unit_domains d "
                "JOIN knowledge_units ku ON ku.id = d.unit_id "
                "WHERE ku.status = 'approved' "
                "GROUP BY d.domain ORDER BY COUNT(*) DESC"
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def pending_queue(
        self, *, limit: int = 20, offset: int = 0
    ) -> list[dict[str, Any]]:
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
                "ORDER BY created_at ASC LIMIT ? OFFSET ?",
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
            row = self._conn.execute(
                "SELECT COUNT(*) FROM knowledge_units WHERE status = 'pending'"
            ).fetchone()
        return row[0]

    def counts_by_status(self) -> dict[str, int]:
        """Return KU counts grouped by review status."""
        self._check_open()
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) FROM knowledge_units GROUP BY status"
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def list_units(
        self,
        *,
        domain: str | None = None,
        confidence_min: float | None = None,
        confidence_max: float | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return KUs with review metadata, filtered by domain, confidence, or status.

        Confidence filtering is applied in-memory after deserialization
        since confidence lives in the JSON blob.

        Args:
            domain: Optional domain tag to filter by.
            confidence_min: Optional minimum confidence (inclusive).
            confidence_max: Optional maximum confidence (exclusive when < 1.0, inclusive at 1.0).
            status: Optional review status to filter by (e.g. "approved", "rejected").

        Returns:
            List of dicts with knowledge_unit, status, reviewed_by,
            and reviewed_at keys.
        """
        self._check_open()
        params: list[str] = []
        conditions: list[str] = []

        if status:
            conditions.append("ku.status = ?")
            params.append(status)

        if domain:
            normalised = normalise_domains([domain])
            if not normalised:
                return []
            conditions.append(
                "ku.id IN ("
                "  SELECT DISTINCT unit_id FROM knowledge_unit_domains WHERE domain = ?"
                ")"
            )
            params.append(normalised[0])

        has_confidence_filter = confidence_min is not None or confidence_max is not None
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql_limit = "" if has_confidence_filter else f"LIMIT {limit}"
        sql = (
            "SELECT ku.data, ku.status, ku.reviewed_by, ku.reviewed_at "
            f"FROM knowledge_units ku {where} "
            f"ORDER BY ku.created_at DESC {sql_limit}"
        )
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()

        results = []
        for row in rows:
            unit = KnowledgeUnit.model_validate_json(row[0])
            c = unit.evidence.confidence
            if confidence_min is not None and c < confidence_min:
                continue
            if confidence_max is not None and (
                c > confidence_max or (c >= confidence_max and confidence_max < 1.0)
            ):
                continue
            results.append(
                {
                    "knowledge_unit": unit,
                    "status": row[1] or "pending",
                    "reviewed_by": row[2],
                    "reviewed_at": row[3],
                }
            )
            if len(results) >= limit:
                break
        return results

    def create_user(self, username: str, password_hash: str) -> None:
        """Insert a new user.

        Args:
            username: The user's login name.
            password_hash: Bcrypt hash of the user's password.

        Raises:
            sqlite3.IntegrityError: If a user with the same username already exists.
        """
        self._check_open()
        now = datetime.now(UTC).isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, now),
            )

    def get_user(self, username: str) -> dict[str, str] | None:
        """Retrieve a user by username.

        Args:
            username: The user's login name.

        Returns:
            A dict with username, password_hash, and created_at keys, or None
            if no user with that username exists.
        """
        self._check_open()
        with self._lock:
            row = self._conn.execute(
                "SELECT username, password_hash, created_at FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if row is None:
            return None
        return {"username": row[0], "password_hash": row[1], "created_at": row[2]}

    def confidence_distribution(self) -> dict[str, int]:
        """Return confidence distribution buckets for approved KUs."""
        self._check_open()
        with self._lock:
            rows = self._conn.execute(
                "SELECT data FROM knowledge_units WHERE status = 'approved'"
            ).fetchall()
        buckets = {"0.0-0.3": 0, "0.3-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
        for (data,) in rows:
            unit = KnowledgeUnit.model_validate_json(data)
            c = unit.evidence.confidence
            if c < 0.3:
                buckets["0.0-0.3"] += 1
            elif c < 0.6:
                buckets["0.3-0.6"] += 1
            elif c < 0.8:
                buckets["0.6-0.8"] += 1
            else:
                buckets["0.8-1.0"] += 1
        return buckets

    def recent_activity(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent activity as one event per knowledge unit.

        Each KU appears once: reviewed KUs show as approved/rejected,
        pending KUs show as proposed.  Ordered by the most recent
        timestamp (reviewed_at for reviewed KUs, created_at otherwise).

        Args:
            limit: Maximum number of activity entries to return.

        Returns:
            List of activity event dicts, newest first.
        """
        self._check_open()
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, data, status, reviewed_by, reviewed_at "
                "FROM knowledge_units "
                "ORDER BY COALESCE(reviewed_at, created_at) DESC LIMIT ?",
                (limit * 2,),
            ).fetchall()
        activity = []
        for row in rows:
            unit = KnowledgeUnit.model_validate_json(row[1])
            proposed_ts = (
                unit.evidence.first_observed.isoformat()
                if unit.evidence.first_observed
                else ""
            )
            # Show only the terminal state per KU: the review event if
            # reviewed, otherwise the proposed event.
            if row[2] in ("approved", "rejected"):
                activity.append(
                    {
                        "type": row[2],
                        "unit_id": row[0],
                        "summary": unit.insight.summary,
                        "reviewed_by": row[3],
                        "timestamp": row[4] or proposed_ts,
                    }
                )
            else:
                activity.append(
                    {
                        "type": "proposed",
                        "unit_id": row[0],
                        "summary": unit.insight.summary,
                        "timestamp": proposed_ts,
                    }
                )
        activity.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return activity[:limit]

    def daily_counts(self, *, days: int = 30) -> list[dict[str, Any]]:
        """Return daily proposal and approval counts with contiguous dates.

        Returns one entry per day from the earliest activity (within the
        lookback window) through today, filling gaps with zero counts.
        Pre-migration rows with NULL created_at are excluded.

        Args:
            days: Number of days to look back.

        Returns:
            List of dicts with date, proposed, approved, and rejected
            counts, ordered ascending.

        Raises:
            ValueError: If days is not positive.
        """
        if days <= 0:
            raise ValueError("days must be positive")
        self._check_open()
        cutoff = f"-{days} days"
        with self._lock:
            proposed_rows = self._conn.execute(
                "SELECT date(created_at) as day, COUNT(*) as cnt "
                "FROM knowledge_units "
                "WHERE created_at >= date('now', ?) "
                "GROUP BY day",
                (cutoff,),
            ).fetchall()
            approved_rows = self._conn.execute(
                "SELECT date(reviewed_at) as day, COUNT(*) as cnt "
                "FROM knowledge_units "
                "WHERE status = 'approved' "
                "AND reviewed_at >= date('now', ?) "
                "GROUP BY day",
                (cutoff,),
            ).fetchall()
            rejected_rows = self._conn.execute(
                "SELECT date(reviewed_at) as day, COUNT(*) as cnt "
                "FROM knowledge_units "
                "WHERE status = 'rejected' "
                "AND reviewed_at >= date('now', ?) "
                "GROUP BY day",
                (cutoff,),
            ).fetchall()
        proposed = {row[0]: row[1] for row in proposed_rows}
        approved = {row[0]: row[1] for row in approved_rows}
        rejected = {row[0]: row[1] for row in rejected_rows}
        all_dates = set(proposed) | set(approved) | set(rejected)
        if not all_dates:
            return []
        start = min(datetime.strptime(d, "%Y-%m-%d").date() for d in all_dates)
        end = datetime.now(UTC).date()
        result: list[dict[str, Any]] = []
        current = start
        while current <= end:
            key = current.isoformat()
            result.append(
                {
                    "date": key,
                    "proposed": proposed.get(key, 0),
                    "approved": approved.get(key, 0),
                    "rejected": rejected.get(key, 0),
                }
            )
            current += timedelta(days=1)
        return result
