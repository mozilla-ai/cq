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

Database URL resolution lives in
`cq_server.db_url.resolve_database_url` and is the single source of
truth for both `alembic/env.py`, the migration runner, and the
runtime store factory (`cq_server.store.create_store`). Precedence:

1. `CQ_DATABASE_URL` — used verbatim. SQLite URLs
   (`sqlite:///<path>`) work today; `postgresql+psycopg://...` is
   reserved for the Postgres backend and currently rejected at
   startup with a `NotImplementedError` pointing at the Phase 2
   child issues ([#311][issue-311] / [#312][issue-312]).
2. `CQ_DB_PATH` — wrapped as `sqlite:///<path>`. The SQLite shortcut
   for single-instance deployments; stays supported indefinitely
   alongside `CQ_DATABASE_URL`.
3. Default — `sqlite:////data/cq.db`.

The `SqliteStore` constructor still calls the legacy
`_ensure_schema()` for safety during the rollout window. Both the
migration and the legacy DDL are idempotent, so running them in
sequence is harmless. The legacy path will be removed in
[issue #310][issue-310] once this PR has deployed everywhere — until
then, any schema change must be added as a new Alembic migration
*and* mirrored in `cq_server/tables.py` / `cq_server/store/_sqlite.py`
to keep the two paths in sync.

To run Alembic commands against a local dev database (the path is
resolved relative to wherever `alembic` is invoked from — here,
`server/backend/`):

```
cd server/backend
CQ_DB_PATH=./dev.db uv run alembic current   # show current revision
CQ_DB_PATH=./dev.db uv run alembic upgrade head
```

The full environment-variable table for self-hosters lives in
[DEVELOPMENT.md](../../DEVELOPMENT.md#self-hosted-server).

[issue-310]: https://github.com/mozilla-ai/cq/issues/310
[issue-311]: https://github.com/mozilla-ai/cq/issues/311
[issue-312]: https://github.com/mozilla-ai/cq/issues/312
