"""Shared DB-setup helpers for cq-server backend tests.

Schema is owned by Alembic — tests that touch the database must run
``run_migrations`` against the file before instantiating ``SqliteStore``.
``init_test_db`` is a one-line wrapper for that idiom.

``build_pre_alembic_schema`` synthesises a legacy production-shape DB
(without an ``alembic_version`` row) so the migration tests can verify
the stamp-on-legacy case.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from cq_server.migrations import run_migrations


def sqlite_url(db: Path) -> str:
    """Return the ``sqlite:///`` URL for a filesystem path."""
    return f"sqlite:///{db}"


def init_test_db(db: Path) -> None:
    """Create the schema in ``db`` via the production Alembic runner."""
    run_migrations(sqlite_url(db))


# Historical pre-Alembic schema, reproduced here as one frozen artifact
# so ``TestExistingPreAlembicDatabase`` can synthesise a legacy
# production DB without depending on the deleted runtime DDL. **Do not
# split into reusable building blocks** — the whole point is that this
# is one immutable snapshot of the pre-Alembic schema (the union of
# what ``_ensure_schema`` + ``ensure_review_columns`` +
# ``ensure_users_table`` + ``ensure_api_keys_table`` used to emit, in
# that order). Anything that wants to reuse a fragment of this should
# instead initialise via ``init_test_db`` (Alembic owns the schema
# now).
_PRE_ALEMBIC_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS knowledge_units (
        id TEXT PRIMARY KEY,
        data TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS knowledge_unit_domains (
        unit_id TEXT NOT NULL,
        domain TEXT NOT NULL,
        FOREIGN KEY (unit_id) REFERENCES knowledge_units(id) ON DELETE CASCADE,
        PRIMARY KEY (unit_id, domain)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_domains_domain ON knowledge_unit_domains(domain)",
    "ALTER TABLE knowledge_units ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'",
    "ALTER TABLE knowledge_units ADD COLUMN reviewed_by TEXT",
    "ALTER TABLE knowledge_units ADD COLUMN reviewed_at TEXT",
    "ALTER TABLE knowledge_units ADD COLUMN created_at TEXT",
    "ALTER TABLE knowledge_units ADD COLUMN tier TEXT NOT NULL DEFAULT 'private'",
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS api_keys (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        labels TEXT NOT NULL DEFAULT '[]',
        key_prefix TEXT NOT NULL,
        key_hash TEXT NOT NULL UNIQUE,
        ttl TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_used_at TEXT,
        revoked_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id)",
)


def build_pre_alembic_schema(db: Path) -> None:
    """Build a production-shape SQLite DB *without* an alembic_version row.

    Reproduces the historical schema that the legacy ``_ensure_schema``
    + ``ensure_*`` startup path used to produce, so the migration tests
    can verify the stamp-on-legacy-DB case without resurrecting deleted
    code. Connection settings (``foreign_keys = ON``) match the
    pragmas applied at runtime.
    """
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        for stmt in _PRE_ALEMBIC_STATEMENTS:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()
