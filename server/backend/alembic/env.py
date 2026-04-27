"""Alembic runtime configuration for the cq server.

The database URL is resolved from the environment via
:func:`cq_server.db_url.resolve_database_url` so that ``alembic``
CLI invocations and startup-time ``command.upgrade`` calls share
the same precedence rules. Programmatic callers (notably
``cq_server.migrations.run_migrations``) may pin a URL on the
Config before invoking Alembic; in that case the pre-set value
wins so tests can target tmp_path-rooted SQLite files without
mutating the process environment.

``render_as_batch=True`` is set in both online and offline modes so
SQLite ALTER TABLE operations work via Alembic's batch recreate
dance. It is harmless on PostgreSQL.

The baseline migration (revision ``0001``) was added in #305. The
runner stamps existing pre-Alembic databases at this revision; new
databases get the migration run normally.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from cq_server.db_url import resolve_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# `set_main_option` routes through ConfigParser, which treats `%` as the
# start of an interpolation token. Fine for SQLite paths today, but a
# Postgres URL with a URL-encoded password (e.g. `p%40ss`) will need
# `%` doubled or a direct pass to `create_engine` when #309 wires this up.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", resolve_database_url())

target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL without a connection."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
