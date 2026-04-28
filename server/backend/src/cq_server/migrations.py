"""Run Alembic migrations at server startup.

Three cases the runner has to handle, all covered by
``run_migrations``:

* New database (no tables) — ``upgrade head`` creates everything via
  the baseline migration.
* Existing pre-Alembic database (``knowledge_units`` exists,
  ``alembic_version`` does not) — ``stamp`` at the baseline so Alembic
  records "the current schema is what the baseline migration would
  have produced", then ``upgrade head`` to apply any later migrations.
* Already-stamped database — ``upgrade head`` is a no-op when there
  are no pending migrations.

The baseline revision id is exported so tests and ops scripts can
reference it without parsing migration files.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

from .db_url import resolve_database_url

__all__ = ["BASELINE_REVISION", "run_migrations"]

_logger = logging.getLogger(__name__)

BASELINE_REVISION = "0001"


def _find_alembic_ini() -> Path:
    """Locate ``alembic.ini`` by walking up from this module.

    The file lives at ``server/backend/alembic.ini`` while this module
    is at ``server/backend/src/cq_server/migrations.py``. Walking
    parents (capped at 5 levels) tolerates layout shifts within the
    package without finding an unrelated ``alembic.ini`` further up the
    filesystem.
    """
    for parent in list(Path(__file__).resolve().parents)[:5]:
        candidate = parent / "alembic.ini"
        if candidate.exists():
            return candidate
    raise RuntimeError("alembic.ini not found near cq_server.migrations module")


_ALEMBIC_INI = _find_alembic_ini()


def _ensure_sqlite_parent_dir(url: str) -> None:
    """Create the parent directory of a sqlite file URL if missing.

    Until #309 wires the runtime store to ``CQ_DATABASE_URL``, the
    server still mkdir's the SQLite parent inside ``SqliteStore``;
    but the migration runs first now, so we hoist the directory
    creation here. No-op for non-sqlite URLs.
    """
    if not url.startswith("sqlite:"):
        return
    # Use SQLAlchemy's URL parser rather than urlparse: it correctly
    # round-trips both absolute (`sqlite:////abs/path`) and relative
    # (`sqlite:///./rel.db`) SQLite URLs to a usable filesystem path,
    # whereas `urlparse(...).path` prefixes a stray `/` that turns
    # `./data/dev.db` into the absolute `/data/dev.db`.
    database = make_url(url).database
    if not database or database == ":memory:":
        return
    Path(database).parent.mkdir(parents=True, exist_ok=True)


def run_migrations(database_url: str | None = None) -> None:
    """Bring the configured database to head, stamping legacy DBs first.

    Assumes a single caller per database — concurrent invocations across
    replicas can race on the table-presence check and on ``upgrade``
    itself. Safe for the current single-instance SQLite deployment;
    #309/#311 will revisit (likely via ``pg_advisory_lock``) when
    Postgres + multi-replica land.

    Args:
        database_url: SQLAlchemy URL to migrate. Defaults to the value
            from :func:`cq_server.db_url.resolve_database_url`, which
            consults ``CQ_DATABASE_URL`` and ``CQ_DB_PATH``.
    """
    url = database_url or resolve_database_url()
    _ensure_sqlite_parent_dir(url)
    redacted = _redact_url(url)

    cfg = Config(str(_ALEMBIC_INI))

    # Hand Alembic a live connection via ``cfg.attributes`` rather than
    # going through ``cfg.set_main_option("sqlalchemy.url", url)``. The
    # latter routes through ConfigParser's interpolation engine, which
    # raises ``ValueError: invalid interpolation syntax`` eagerly on any
    # literal ``%`` in the URL — a foot-gun once URL-encoded passwords
    # land with Postgres in #309/#311, and already triggerable today by
    # a SQLite filename containing ``%``. ``env.py`` picks up the
    # connection before it tries to build its own engine.
    engine = create_engine(url)
    try:
        # ``engine.begin()`` (not ``connect()``) so the alembic_version
        # row written by stamp/upgrade actually commits at block exit —
        # this matches the Alembic cookbook recipe for "sharing a
        # connection with a series of migration commands."
        with engine.begin() as connection:
            tables = set(inspect(connection).get_table_names())
            cfg.attributes["connection"] = connection

            if "alembic_version" not in tables and "knowledge_units" in tables:
                # Pre-Alembic prod DB: the schema already exists, just
                # record that we're at baseline so ``upgrade head``
                # doesn't re-run the CREATE TABLE statements (which
                # would fail).
                _logger.info(
                    "Pre-Alembic database detected at %s; stamping at baseline %s",
                    redacted,
                    BASELINE_REVISION,
                )
                command.stamp(cfg, BASELINE_REVISION)

            _logger.info("Running Alembic upgrade head against %s", redacted)
            command.upgrade(cfg, "head")
    finally:
        engine.dispose()


def _redact_url(url: str) -> str:
    """Return a log-safe rendering of the URL with the password masked."""
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:  # noqa: BLE001 — never let logging break startup
        return "<unparseable url>"
