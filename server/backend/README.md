# cq-server backend

FastAPI service backing the cq remote store.

## Development

From the repository root:

```
make setup-server-backend   # uv sync
make dev-api                # run against a local SQLite DB
make test-server-backend    # pytest
make lint-server-backend    # pre-commit (ruff, ty, uv lock check)
```

## Database migrations (Alembic)

The server runs Alembic migrations on every start, before opening the
store. The runner (`cq_server.migrations.run_migrations`) handles
three cases:

1. **New database** (no tables) — applies the baseline migration,
   creating every table from scratch. The `alembic_version` row is
   written as part of that.
2. **Existing pre-Alembic database** (data tables present, no
   `alembic_version`) — *stamps* the baseline revision without
   re-running its DDL, then runs any later migrations. This is the
   first-restart-after-upgrade case for a server that's been running
   on the legacy `_ensure_schema()` path. **No DDL re-runs, no data
   touched, no downtime** — the change is a single insert into a new
   table.
3. **Already-managed database** — `upgrade head` is a no-op when
   there are no pending revisions, so restart is idempotent.

Database URL resolution (used by `alembic/env.py`, the migration
runner, and — in a later child issue — the runtime store factory)
lives in `cq_server.db_url.resolve_database_url`. Precedence:

1. `CQ_DATABASE_URL` — used verbatim (e.g. `postgresql+psycopg://…`).
2. `CQ_DB_PATH` — wrapped as `sqlite:///<path>` (back-compat with
   the existing env var).
3. Default — `sqlite:////data/cq.db`.

The `RemoteStore` constructor still calls the legacy
`_ensure_schema()` for safety during the rollout window. Both the
migration and the legacy DDL are idempotent, so running them in
sequence is harmless. The legacy path will be removed in
[issue #310][issue-310] once this PR has deployed everywhere — until
then, any schema change must be added as a new Alembic migration
*and* mirrored in `cq_server/tables.py` / `cq_server/store/__init__.py`
to keep the two paths in sync.

To run Alembic commands against a local dev database (the path is
resolved relative to wherever `alembic` is invoked from — here,
`server/backend/`):

```
cd server/backend
CQ_DB_PATH=./dev.db uv run alembic current   # show current revision
CQ_DB_PATH=./dev.db uv run alembic upgrade head
```

Full environment-variable documentation will land alongside the
`CQ_DATABASE_URL` runtime wiring in a later phase-1 child issue.

[epic](https://github.com/mozilla-ai/cq/issues/257)
