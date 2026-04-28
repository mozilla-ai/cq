"""Baseline schema.

Revision ID: 0001
Revises:
Create Date: 2026-04-25

Reverse-engineered from the current production SQLite schema — i.e.
the union of:

  - ``cq_server.store._SCHEMA_SQL`` (knowledge_units, knowledge_unit_domains,
    idx_domains_domain).
  - ``cq_server.tables._REVIEW_COLUMN_STATEMENTS`` (the trailing ALTER
    TABLE … ADD COLUMN suite that grew the review/tier columns).
  - ``cq_server.tables.USERS_TABLE_SQL`` and ``API_KEYS_TABLE_SQL``.

Existing pre-Alembic databases are stamped at this revision in
``cq_server.migrations.run_migrations`` rather than upgraded into it,
so the column order and constraints below must match what's already
on disk in production. **Do not edit this migration after merge** —
production DBs will be stamped at this revision and any change here
will diverge from what's actually on disk. Add a new migration file
instead.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the production schema from scratch."""
    # Order: id, data, then the historical ALTER-added columns in the
    # exact order they were added on prod
    # (status, reviewed_by, reviewed_at, created_at, tier).
    op.create_table(
        "knowledge_units",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=True),
        sa.Column(
            "tier",
            sa.Text(),
            nullable=False,
            server_default="private",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "knowledge_unit_domains",
        sa.Column("unit_id", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["unit_id"], ["knowledge_units.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("unit_id", "domain"),
    )
    op.create_index("idx_domains_domain", "knowledge_unit_domains", ["domain"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("username"),
        # SQLite-specific: emit the AUTOINCREMENT keyword so the rowid
        # monotonicity guarantee matches the legacy schema. No-op on
        # PostgreSQL (uses SERIAL/IDENTITY automatically).
        sqlite_autoincrement=True,
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("labels", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("key_prefix", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("ttl", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("last_used_at", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_api_keys_user", "api_keys", ["user_id"])


def downgrade() -> None:
    """Drop everything the upgrade created. Never used in production."""
    op.drop_index("idx_api_keys_user", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_table("users")
    op.drop_index("idx_domains_domain", table_name="knowledge_unit_domains")
    op.drop_table("knowledge_unit_domains")
    op.drop_table("knowledge_units")
