"""Shared SQLAlchemy Core query helpers for portable cq server queries.

Centralises every SQL statement that is portable between SQLite and
PostgreSQL. The repository classes in this package compose these helpers
for the boring queries. The few statements that diverge by dialect are
kept as ``{"sqlite": ..., "postgresql": ...}`` dicts (here and in the
repos) and resolved once from ``engine.dialect.name`` in each repo's
``__init__`` — there is no per-dialect ``Store`` class.

The module is pure: no engine, no connection, no metadata. Statements are
either:

* Module-level :class:`~sqlalchemy.sql.expression.TextClause` constants
  for static queries, with named ``:placeholder`` parameters.
* Small builder functions returning a ``TextClause`` for queries whose
  shape depends on caller arguments (variable IN-list or conditional
  WHERE).

Callers bind named parameters at execute time. Out of scope here:
PRAGMAs, ``pg_advisory_lock``, vector (sqlite-vec / pgvector), full-text
(FTS5 / ``tsvector``). Those live in their respective concrete stores.

``daily_counts`` filters by a Python-computed ``:cutoff`` ISO date string
(the SQLite-specific ``date('now', '-N days')`` form was removed per RFC
#275), but the day-truncation half is dialect-specific: PostgreSQL has no
``date(text)`` overload, so the daily-count helpers below are keyed by
dialect (``date(<textcol>)`` on SQLite; ``to_char(<textcol>::timestamptz,
'YYYY-MM-DD')`` on PostgreSQL). See ``_daily`` for detail. Phase 3 (#317)
migrates PG timestamps to ``TIMESTAMP WITH TIME ZONE`` and can retire the cast.
"""

from __future__ import annotations

from sqlalchemy import bindparam
from sqlalchemy.sql.expression import TextClause, text

# --- knowledge_units --------------------------------------------------------

INSERT_UNIT: TextClause = text(
    "INSERT INTO knowledge_units (id, data, created_at, tier) VALUES (:id, :data, :created_at, :tier)"
)

INSERT_UNIT_DOMAIN: TextClause = text("INSERT INTO knowledge_unit_domains (unit_id, domain) VALUES (:unit_id, :domain)")

DELETE_UNIT_DOMAINS: TextClause = text("DELETE FROM knowledge_unit_domains WHERE unit_id = :unit_id")

SELECT_APPROVED_BY_ID: TextClause = text("SELECT data FROM knowledge_units WHERE id = :id AND status = 'approved'")

SELECT_BY_ID: TextClause = text("SELECT data FROM knowledge_units WHERE id = :id")

SELECT_REVIEW_STATUS_BY_ID: TextClause = text(
    "SELECT status, reviewed_by, reviewed_at FROM knowledge_units WHERE id = :id"
)

UPDATE_REVIEW_STATUS: TextClause = text(
    "UPDATE knowledge_units SET status = :status, reviewed_by = :reviewed_by, reviewed_at = :reviewed_at WHERE id = :id"
)

UPDATE_UNIT_DATA: TextClause = text("UPDATE knowledge_units SET data = :data, tier = :tier WHERE id = :id")

SELECT_TOTAL_COUNT: TextClause = text("SELECT COUNT(*) FROM knowledge_units")

SELECT_DOMAIN_COUNTS: TextClause = text(
    "SELECT d.domain, COUNT(*) "
    "FROM knowledge_unit_domains d "
    "JOIN knowledge_units ku ON ku.id = d.unit_id "
    "WHERE ku.status = 'approved' "
    "GROUP BY d.domain "
    "ORDER BY COUNT(*) DESC"
)

SELECT_PENDING_QUEUE: TextClause = text(
    "SELECT data, status, reviewed_by, reviewed_at "
    "FROM knowledge_units WHERE status = 'pending' "
    "ORDER BY created_at ASC LIMIT :limit OFFSET :offset"
)

SELECT_PENDING_COUNT: TextClause = text("SELECT COUNT(*) FROM knowledge_units WHERE status = 'pending'")

SELECT_COUNTS_BY_STATUS: TextClause = text("SELECT status, COUNT(*) FROM knowledge_units GROUP BY status")

SELECT_COUNTS_BY_TIER: TextClause = text(
    "SELECT tier, COUNT(*) FROM knowledge_units WHERE status = 'approved' GROUP BY tier"
)

SELECT_APPROVED_DATA: TextClause = text("SELECT data FROM knowledge_units WHERE status = 'approved'")

# Callers typically bind ``:limit`` to ``activity_limit * 2``: the result
# is re-sorted in Python by ``COALESCE(reviewed_at, created_at)`` and then
# truncated, so over-fetching keeps the truncation honest when many KUs
# have been reviewed since the most recent one was created. See
# ``ReviewRepository.recent_activity``.
SELECT_RECENT_ACTIVITY: TextClause = text(
    "SELECT id, data, status, reviewed_by, reviewed_at "
    "FROM knowledge_units "
    "ORDER BY COALESCE(reviewed_at, created_at) DESC LIMIT :limit"
)

# `daily_counts()` — three queries that filter by a Python-computed date
# string. The SQLite-specific `date('now', ?)` form is removed per RFC #275;
# callers compute
# `cutoff = (datetime.now(UTC) - timedelta(days=...)).date().isoformat()`.
#
# Dialect-keyed and NON-PORTABLE. These run against a TEXT timestamp column
# through Phase 2:
#   * SQLite parses the ISO string natively with `date(<textcol>)`, which
#     returns a 'YYYY-MM-DD' string.
#   * PostgreSQL has no `date(text)` overload, so we cast the TEXT column to
#     `timestamptz` then format it with `to_char(..., 'YYYY-MM-DD')` so the day
#     key comes back as the same 'YYYY-MM-DD' string SQLite yields. `to_char`
#     is used rather than `::date::text` because the latter formats per session
#     `DateStyle` (e.g. '01.07.2026' under `German`), which would break the
#     caller's `strptime(day, "%Y-%m-%d")`; `to_char` is DateStyle-independent.
#     The engine is pinned to UTC (see `core.db.Database`) so the truncation
#     matches SQLite's UTC ISO strings. Phase 3 (#317) migrates PG timestamps
#     to `TIMESTAMP WITH TIME ZONE` and removes the cast. The `>= :cutoff` half
#     is portable (Python-computed ISO string) either way.


def _daily(column: str, status_clause: str) -> dict[str, TextClause]:
    """Build the dialect-keyed daily-count query for one timestamp column.

    ``column`` and ``status_clause`` are interpolated into the SQL text, so
    callers must pass only trusted literal column names / clauses (they do:
    the three module-level constants below are the only call sites).
    """
    return {
        "sqlite": text(
            f"SELECT date({column}) AS day, COUNT(*) AS cnt "
            f"FROM knowledge_units WHERE {status_clause}{column} >= :cutoff GROUP BY day"
        ),
        "postgresql": text(
            f"SELECT to_char(({column}::timestamptz), 'YYYY-MM-DD') AS day, COUNT(*) AS cnt "
            f"FROM knowledge_units WHERE {status_clause}{column} >= :cutoff GROUP BY day"
        ),
    }


SELECT_PROPOSED_DAILY: dict[str, TextClause] = _daily("created_at", "")
SELECT_APPROVED_DAILY: dict[str, TextClause] = _daily("reviewed_at", "status = 'approved' AND ")
SELECT_REJECTED_DAILY: dict[str, TextClause] = _daily("reviewed_at", "status = 'rejected' AND ")


def confidence_distribution_sql(buckets: list[tuple[float, str]], dialect: str) -> TextClause:
    """Build the approved-unit confidence-distribution query for one dialect.

    ``buckets`` is ``(exclusive upper bound, label)`` ordered low-to-high; the
    last entry is the ``inf`` catch-all (its bound is ignored, its label is the
    ``ELSE``). The bounds/labels are interpolated into the SQL, so callers must
    pass only the trusted literal bucket list defined in the repo.

    COALESCE to 0.5 mirrors the ``Evidence.confidence`` default, so a row whose
    JSON omits the field buckets identically instead of hitting the catch-all.
    SQLite reads the JSON blob with ``json_extract``; PostgreSQL casts the TEXT
    column to ``jsonb``, extracts with ``#>>``, and must alias the derived
    subquery (``AS sub``) — PG rejects an unnamed FROM-subquery.
    """
    extract = {
        "sqlite": "json_extract(data, '$.evidence.confidence')",
        "postgresql": "(data::jsonb #>> '{evidence,confidence}')::numeric",
    }[dialect]
    alias = " AS sub" if dialect == "postgresql" else ""
    whens = " ".join(f"WHEN confidence < {bound} THEN '{label}'" for bound, label in buckets[:-1])
    return text(
        f"SELECT CASE {whens} ELSE '{buckets[-1][1]}' END AS bucket, COUNT(*) AS cnt "
        f"FROM (SELECT COALESCE({extract}, 0.5) AS confidence "
        f"FROM knowledge_units WHERE status = 'approved'){alias} "
        "GROUP BY bucket"
    )


# Variable IN-list for ``KnowledgeRepository.query``. Bind ``:domains`` to the list
# of normalised domain strings; SQLAlchemy expands it at execute time.
# Empty list: SQLAlchemy 2.0 rewrites ``IN ()`` to a no-rows subquery
# (``IN (SELECT 1 FROM (SELECT 1) WHERE 1!=1)``) and the helper returns
# zero rows — no raise. Callers may still short-circuit for a fast-path
# but it is not required for correctness.
SELECT_QUERY_UNITS: TextClause = text(
    "SELECT ku.data "
    "FROM knowledge_units ku "
    "WHERE ku.status = 'approved' "
    "AND ku.id IN ("
    "SELECT DISTINCT unit_id FROM knowledge_unit_domains WHERE domain IN :domains"
    ")"
).bindparams(bindparam("domains", expanding=True))


def select_list_units(*, domain: str | None, status: str | None, apply_limit: bool) -> TextClause:
    """Build the SELECT for ``ReviewRepository.list_units``.

    Pure SQL builder — does no normalization, the caller owns it. WHERE
    conditions on ``status`` and ``domain`` are inlined only when the
    argument is non-``None``; an empty or whitespace-only string is
    treated as a *real* filter value and binds literally (returning zero
    rows). To mirror ``ReviewRepository.list_units``, callers must (a) pass
    ``None`` when the user-supplied filter is empty/whitespace, and (b)
    run ``domain`` through ``normalize_domains`` (lowercase + strip)
    first. ``apply_limit`` controls whether SQL-side ``LIMIT`` is
    applied: skip it when confidence filtering is in effect because
    confidence lives inside the JSON blob and is filtered in Python.

    Caller binds ``:status`` and ``:domain`` only for conditions that are
    enabled; ``:limit`` only when ``apply_limit`` is true.
    """
    conditions: list[str] = []
    if status is not None:
        conditions.append("ku.status = :status")
    if domain is not None:
        conditions.append("ku.id IN (SELECT DISTINCT unit_id FROM knowledge_unit_domains WHERE domain = :domain)")
    parts: list[str] = ["SELECT ku.data, ku.status, ku.reviewed_by, ku.reviewed_at FROM knowledge_units ku"]
    if conditions:
        parts.append(f"WHERE {' AND '.join(conditions)}")
    parts.append("ORDER BY ku.created_at DESC")
    if apply_limit:
        parts.append("LIMIT :limit")
    return text(" ".join(parts))


# --- users ------------------------------------------------------------------

INSERT_USER: TextClause = text(
    "INSERT INTO users (username, password_hash, created_at) VALUES (:username, :password_hash, :created_at)"
)

SELECT_USER_BY_USERNAME: TextClause = text(
    "SELECT id, username, password_hash, created_at FROM users WHERE username = :username"
)

# --- api_keys ---------------------------------------------------------------

COUNT_ACTIVE_KEYS_FOR_USER: TextClause = text(
    "SELECT COUNT(*) FROM api_keys WHERE user_id = :user_id AND revoked_at IS NULL AND expires_at > :now"
)

INSERT_API_KEY: TextClause = text(
    "INSERT INTO api_keys "
    "(id, user_id, name, labels, key_prefix, key_hash, ttl, expires_at, created_at) "
    "VALUES (:id, :user_id, :name, :labels, :key_prefix, :key_hash, :ttl, :expires_at, :created_at)"
)

SELECT_KEY_FOR_USER: TextClause = text(
    "SELECT id, user_id, name, labels, key_prefix, ttl, expires_at, "
    "created_at, last_used_at, revoked_at "
    "FROM api_keys WHERE id = :key_id AND user_id = :user_id"
)

SELECT_ACTIVE_KEY_BY_ID: TextClause = text(
    "SELECT k.id, k.user_id, u.username, k.name, k.labels, k.key_prefix, "
    "k.key_hash, k.ttl, k.expires_at, k.created_at, k.last_used_at, k.revoked_at "
    "FROM api_keys k JOIN users u ON u.id = k.user_id "
    "WHERE k.id = :key_id AND k.revoked_at IS NULL AND k.expires_at > :now"
)

LIST_KEYS_FOR_USER: TextClause = text(
    "SELECT id, name, labels, key_prefix, ttl, expires_at, created_at, last_used_at, revoked_at "
    "FROM api_keys WHERE user_id = :user_id ORDER BY created_at DESC"
)

UPDATE_KEY_REVOKE: TextClause = text(
    "UPDATE api_keys SET revoked_at = :now WHERE id = :key_id AND user_id = :user_id AND revoked_at IS NULL"
)

UPDATE_KEY_LAST_USED: TextClause = text("UPDATE api_keys SET last_used_at = :now WHERE id = :key_id")
