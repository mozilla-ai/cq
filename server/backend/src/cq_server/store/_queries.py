"""Shared SQLAlchemy Core query helpers for portable cq server queries.

Centralises every SQL statement that is portable between SQLite and
PostgreSQL. Concrete ``Store`` implementations (``SqliteStore``,
``PostgresStore``) compose these helpers for the boring queries while
keeping dialect-specific code (PRAGMAs, advisory locks, vector search,
full-text search) inside their own classes.

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

``daily_counts`` is portable when the date cutoff is computed in Python
and passed in as a ``:cutoff`` ISO date string; the SQLite-specific
``date('now', '-N days')`` form has been removed here per RFC #275.

Load-bearing assumption — ``date(reviewed_at)`` / ``date(created_at)`` in
the daily-count helpers below: these run against ``TEXT`` columns through
Phase 2. SQLite's ``date()`` parses ISO strings natively. PostgreSQL has
no ``date(text)`` overload, but with the default ``DateStyle=ISO`` it
implicit-casts ISO-8601-with-offset strings to ``timestamptz`` before
applying the built-in ``date(timestamp)`` function. Operators running PG
under a non-default ``DateStyle`` may see this fail. Phase 3 (#317)
removes this dependency by migrating PG timestamps to
``TIMESTAMP WITH TIME ZONE``; SQLite continues to store ISO strings.
After #317 the same SQL is portable through two distinct mechanisms.
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
# ``RemoteStore.recent_activity``.
SELECT_RECENT_ACTIVITY: TextClause = text(
    "SELECT id, data, status, reviewed_by, reviewed_at "
    "FROM knowledge_units "
    "ORDER BY COALESCE(reviewed_at, created_at) DESC LIMIT :limit"
)

# `daily_counts()` — three queries that filter by a Python-computed date
# string. The SQLite-specific `date('now', ?)` form is removed per RFC #275;
# callers compute
# `cutoff = (datetime.now(UTC) - timedelta(days=...)).date().isoformat()`.

SELECT_PROPOSED_DAILY: TextClause = text(
    "SELECT date(created_at) AS day, COUNT(*) AS cnt FROM knowledge_units WHERE created_at >= :cutoff GROUP BY day"
)

SELECT_APPROVED_DAILY: TextClause = text(
    "SELECT date(reviewed_at) AS day, COUNT(*) AS cnt "
    "FROM knowledge_units "
    "WHERE status = 'approved' AND reviewed_at >= :cutoff GROUP BY day"
)

SELECT_REJECTED_DAILY: TextClause = text(
    "SELECT date(reviewed_at) AS day, COUNT(*) AS cnt "
    "FROM knowledge_units "
    "WHERE status = 'rejected' AND reviewed_at >= :cutoff GROUP BY day"
)

# Variable IN-list for ``RemoteStore.query``. Bind ``:domains`` to the list
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
    """Build the SELECT for ``RemoteStore.list_units``.

    Pure SQL builder — does no normalization, the caller owns it. WHERE
    conditions on ``status`` and ``domain`` are inlined only when the
    argument is non-``None``; an empty or whitespace-only string is
    treated as a *real* filter value and binds literally (returning zero
    rows). To mirror ``RemoteStore.list_units``, callers must (a) pass
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
