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

from pathlib import Path
from urllib.parse import urlparse

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from .db_url import resolve_database_url

__all__ = ["BASELINE_REVISION", "run_migrations"]

BASELINE_REVISION = "0001"

# alembic.ini lives at the package backend root: server/backend/alembic.ini.
# This module is at server/backend/src/cq_server/migrations.py — three
# parents up from __file__ gets us to server/backend/.
_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _ensure_sqlite_parent_dir(url: str) -> None:
    """Create the parent directory of a sqlite file URL if missing.

    Until #309 wires the runtime store to ``CQ_DATABASE_URL``, the
    server still mkdir's the SQLite parent inside ``RemoteStore``;
    but the migration runs first now, so we hoist the directory
    creation here. No-op for non-sqlite URLs.
    """
    if not url.startswith("sqlite:"):
        return
    parsed = urlparse(url)
    # `sqlite:///abs/path` → parsed.path == '/abs/path'
    # `sqlite:///./rel.db` → parsed.path == '/./rel.db'
    # `sqlite://` (in-memory)→ parsed.path == ''
    if not parsed.path or parsed.path == "/:memory:":
        return
    Path(parsed.path).parent.mkdir(parents=True, exist_ok=True)


def run_migrations(database_url: str | None = None) -> None:
    """Bring the configured database to head, stamping legacy DBs first.

    Args:
        database_url: SQLAlchemy URL to migrate. Defaults to the value
            from :func:`cq_server.db_url.resolve_database_url`, which
            consults ``CQ_DATABASE_URL`` and ``CQ_DB_PATH``.
    """
    url = database_url or resolve_database_url()
    _ensure_sqlite_parent_dir(url)

    cfg = Config(str(_ALEMBIC_INI))
    # ConfigParser interpolation caveat: `%` in URLs (e.g. URL-encoded
    # passwords) would need doubling here. Harmless for SQLite paths;
    # #309/#311 will revisit when Postgres URLs land at runtime.
    cfg.set_main_option("sqlalchemy.url", url)

    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    if "alembic_version" not in tables and "knowledge_units" in tables:
        # Pre-Alembic prod DB: the schema already exists, just record
        # that we're at baseline so `upgrade head` doesn't re-run the
        # CREATE TABLE statements (which would fail).
        command.stamp(cfg, BASELINE_REVISION)

    command.upgrade(cfg, "head")
