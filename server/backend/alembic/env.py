"""Alembic runtime configuration for the cq server.

Both entry points — startup (``cq_server.migrations.run_migrations``)
and the ``alembic`` CLI — must avoid round-tripping the database URL
through ConfigParser. ``Config.set_main_option`` runs interpolation
eagerly and raises on any literal ``%`` (URL-encoded passwords,
SQLite filenames with ``%``, etc.).

The runtime path hands a live connection in via
``config.attributes["connection"]`` and we use it directly. The CLI
path resolves the URL at use-time via
:func:`cq_server.db_url.resolve_database_url` and builds its own
engine — never going through ``set_main_option``.

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
from sqlalchemy import create_engine, pool

from cq_server.db_url import resolve_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _resolve_url() -> str:
    """Return the database URL without going through ConfigParser.

    A URL pinned on the Config (via ``set_main_option``) would win, but
    no caller does that any more — the runtime hands a connection in
    via ``cfg.attributes["connection"]``. Falling back to env-var
    resolution covers the CLI path (``alembic upgrade head``).
    """
    pinned = config.get_main_option("sqlalchemy.url")
    if pinned:
        return pinned
    return resolve_database_url()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL without a connection."""
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — against a live connection.

    Two cases:

    * The runtime caller (``cq_server.migrations.run_migrations``)
      attaches an already-open connection to
      ``config.attributes["connection"]``. Use it directly so the URL
      never touches ConfigParser.
    * The CLI path (``alembic upgrade head``) supplies no connection;
      build the engine programmatically from ``_resolve_url`` rather
      than via ``engine_from_config``, which would re-introduce the
      ConfigParser interpolation hazard for any ``%`` in the URL.
    """
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(_resolve_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as conn:
            context.configure(
                connection=conn,
                target_metadata=target_metadata,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
