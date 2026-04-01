"""Database schema definitions and migration logic."""

import sqlite3

_REVIEW_COLUMN_STATEMENTS = [
    "ALTER TABLE knowledge_units ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'",
    "ALTER TABLE knowledge_units ADD COLUMN reviewed_by TEXT",
    "ALTER TABLE knowledge_units ADD COLUMN reviewed_at TEXT",
    "ALTER TABLE knowledge_units ADD COLUMN created_at TEXT",
]

USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def ensure_review_columns(conn: sqlite3.Connection) -> None:
    """Add review status columns if they do not exist."""
    cursor = conn.execute("PRAGMA table_info(knowledge_units)")
    existing = {row[1] for row in cursor.fetchall()}
    for statement in _REVIEW_COLUMN_STATEMENTS:
        col = statement.split("COLUMN ")[1].split()[0]
        if col not in existing:
            conn.execute(statement)
    conn.commit()


def ensure_users_table(conn: sqlite3.Connection) -> None:
    """Create the users table if it does not exist."""
    conn.executescript(USERS_TABLE_SQL)
