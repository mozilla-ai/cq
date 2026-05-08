"""Review repository: review-status transitions, queue, and dashboard aggregations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from cq.models import KnowledgeUnit

from ..core.db import Database
from ._queries import (
    SELECT_APPROVED_DAILY,
    SELECT_APPROVED_DATA,
    SELECT_COUNTS_BY_STATUS,
    SELECT_PENDING_COUNT,
    SELECT_PENDING_QUEUE,
    SELECT_PROPOSED_DAILY,
    SELECT_RECENT_ACTIVITY,
    SELECT_REJECTED_DAILY,
    SELECT_REVIEW_STATUS_BY_ID,
    UPDATE_REVIEW_STATUS,
    select_list_units,
)


class ReviewRepository:
    """Read/write access to review queue, decisions, and dashboard metrics."""

    def __init__(self, db: Database) -> None:
        """Wire the repository to the shared ``Database``."""
        self._db = db

    async def confidence_distribution(self) -> dict[str, int]:
        """Return approved-unit counts grouped into four confidence buckets."""
        return await self._db.run_sync(self._confidence_distribution_sync)

    async def counts_by_status(self) -> dict[str, int]:
        """Return total counts per review status (pending/approved/rejected)."""
        return await self._db.run_sync(self._counts_by_status_sync)

    async def daily_counts(self, *, days: int = 30) -> list[dict[str, Any]]:
        """Return daily proposed/approved/rejected counts across ``days`` days."""
        if days <= 0:
            raise ValueError("days must be positive")
        return await self._db.run_sync(self._daily_counts_sync, days=days)

    async def get_status(self, unit_id: str) -> dict[str, str | None] | None:
        """Return the review row (status, reviewed_by, reviewed_at) or ``None``."""
        return await self._db.run_sync(self._get_status_sync, unit_id)

    async def list_units(
        self,
        *,
        domain: str | None = None,
        confidence_min: float | None = None,
        confidence_max: float | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return units filtered by domain/status/confidence range."""
        return await self._db.run_sync(
            self._list_units_sync,
            domain=domain,
            confidence_min=confidence_min,
            confidence_max=confidence_max,
            status=status,
            limit=limit,
        )

    async def pending_count(self) -> int:
        """Return the total number of units awaiting review."""
        return await self._db.run_sync(self._pending_count_sync)

    async def pending_queue(self, *, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        """Return a page of pending units oldest-first."""
        return await self._db.run_sync(self._pending_queue_sync, limit=limit, offset=offset)

    async def recent_activity(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the latest proposal/approval/rejection events."""
        return await self._db.run_sync(self._recent_activity_sync, limit=limit)

    async def set_status(self, unit_id: str, status: str, reviewed_by: str) -> None:
        """Record the reviewer decision; raises ``KeyError`` if the unit is unknown."""
        await self._db.run_sync(self._set_status_sync, unit_id, status, reviewed_by)

    def _confidence_distribution_sync(self) -> dict[str, int]:
        buckets = {"0.0-0.3": 0, "0.3-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
        with self._db.engine.connect() as conn:
            rows = conn.execute(SELECT_APPROVED_DATA).fetchall()
        for row in rows:
            c = KnowledgeUnit.model_validate_json(row[0]).evidence.confidence
            if c < 0.3:
                buckets["0.0-0.3"] += 1
            elif c < 0.6:
                buckets["0.3-0.6"] += 1
            elif c < 0.8:
                buckets["0.6-0.8"] += 1
            else:
                buckets["0.8-1.0"] += 1
        return buckets

    def _counts_by_status_sync(self) -> dict[str, int]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(SELECT_COUNTS_BY_STATUS).fetchall()
        return {row[0]: row[1] for row in rows}

    def _daily_counts_sync(self, *, days: int) -> list[dict[str, Any]]:
        cutoff = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
        with self._db.engine.connect() as conn:
            proposed = {row[0]: row[1] for row in conn.execute(SELECT_PROPOSED_DAILY, {"cutoff": cutoff}).fetchall()}
            approved = {row[0]: row[1] for row in conn.execute(SELECT_APPROVED_DAILY, {"cutoff": cutoff}).fetchall()}
            rejected = {row[0]: row[1] for row in conn.execute(SELECT_REJECTED_DAILY, {"cutoff": cutoff}).fetchall()}
        all_dates = set(proposed) | set(approved) | set(rejected)
        if not all_dates:
            return []
        start = min(datetime.strptime(d, "%Y-%m-%d").date() for d in all_dates)
        end = datetime.now(UTC).date()
        rows: list[dict[str, Any]] = []
        current = start
        while current <= end:
            key = current.isoformat()
            rows.append(
                {
                    "date": key,
                    "proposed": proposed.get(key, 0),
                    "approved": approved.get(key, 0),
                    "rejected": rejected.get(key, 0),
                }
            )
            current += timedelta(days=1)
        return rows

    def _get_status_sync(self, unit_id: str) -> dict[str, str | None] | None:
        with self._db.engine.connect() as conn:
            row = conn.execute(SELECT_REVIEW_STATUS_BY_ID, {"id": unit_id}).fetchone()
        if row is None:
            return None
        return {"status": row[0], "reviewed_by": row[1], "reviewed_at": row[2]}

    def _list_units_sync(
        self,
        *,
        domain: str | None,
        confidence_min: float | None,
        confidence_max: float | None,
        status: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        normalized_domain: str | None = None
        if domain is not None and domain.strip():
            normalized_domain = domain.strip().lower()

        normalized_status: str | None = status if (status is not None and status.strip()) else None

        confidence_filter_active = confidence_min is not None or confidence_max is not None
        stmt = select_list_units(
            domain=normalized_domain,
            status=normalized_status,
            apply_limit=not confidence_filter_active,
        )
        params: dict[str, Any] = {}
        if normalized_domain is not None:
            params["domain"] = normalized_domain
        if normalized_status is not None:
            params["status"] = normalized_status
        if not confidence_filter_active:
            params["limit"] = limit

        with self._db.engine.connect() as conn:
            rows = conn.execute(stmt, params).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            unit = KnowledgeUnit.model_validate_json(row[0])
            c = unit.evidence.confidence
            if confidence_min is not None and c < confidence_min:
                continue
            if confidence_max is not None and (c > confidence_max or (c >= confidence_max and confidence_max < 1.0)):
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

    def _pending_count_sync(self) -> int:
        with self._db.engine.connect() as conn:
            return int(conn.execute(SELECT_PENDING_COUNT).scalar() or 0)

    def _pending_queue_sync(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(SELECT_PENDING_QUEUE, {"limit": limit, "offset": offset}).fetchall()
        return [
            {
                "knowledge_unit": KnowledgeUnit.model_validate_json(row[0]),
                "status": row[1] or "pending",
                "reviewed_by": row[2],
                "reviewed_at": row[3],
            }
            for row in rows
        ]

    def _recent_activity_sync(self, *, limit: int) -> list[dict[str, Any]]:
        # Over-fetch by 2x to give buffer; the SELECT already ORDER BYs
        # COALESCE(reviewed_at, created_at) DESC. Final slice trims to limit.
        with self._db.engine.connect() as conn:
            rows = conn.execute(SELECT_RECENT_ACTIVITY, {"limit": limit * 2}).fetchall()
        activity: list[dict[str, Any]] = []
        for row in rows:
            unit = KnowledgeUnit.model_validate_json(row[1])
            proposed_ts = unit.evidence.first_observed.isoformat() if unit.evidence.first_observed else ""
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
        return activity[:limit]

    def _set_status_sync(self, unit_id: str, status: str, reviewed_by: str) -> None:
        reviewed_at = datetime.now(UTC).isoformat()
        with self._db.engine.begin() as conn:
            cursor = conn.execute(
                UPDATE_REVIEW_STATUS,
                {"id": unit_id, "status": status, "reviewed_by": reviewed_by, "reviewed_at": reviewed_at},
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Knowledge unit not found: {unit_id}")
