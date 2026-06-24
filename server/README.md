# cq-server backend

{% hint style="info" icon="tag" %}
Version: v0.9.0
{% endhint %}

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

Alembic owns the schema. The server runs `alembic upgrade head` on
every start, before opening the store; any schema change must land as
a new migration in `alembic/versions/`.

The runner (`cq_server.migrations.run_migrations`) is restart-safe in
three cases:

1. **New database** — applies the baseline migration and writes
   `alembic_version`.
2. **Database with existing data but no `alembic_version`** — stamps
   the baseline revision without re-running its DDL, then applies any
   later migrations. No data touched.
3. **Already-managed database** — `upgrade head` is a no-op when
   nothing is pending.

### Database URL

Resolution lives in `cq_server.core.config.Settings.resolved_database_url`
and is the single source of truth for `alembic/env.py`, the migration
runner, and the ``Database`` engine wrapper. Precedence:

1. `CQ_DATABASE_URL` — used verbatim. SQLite URLs (`sqlite:///<path>`)
   work today; `postgresql+psycopg://...` is reserved for the Postgres
   backend and currently raises `NotImplementedError` at startup
   pointing at the Phase 2 implementation issue ([#312][issue-312]).
2. `CQ_DB_PATH` — wrapped as `sqlite:///<path>`. The SQLite shortcut
   for single-instance deployments; supported alongside
   `CQ_DATABASE_URL`.
3. Default — `sqlite:////data/cq.db`.

### Rollback

Migrations are forward-only. If a new migration causes a bad deploy,
redeploy the previous server image; if its head is older than the
`alembic_version` row on disk, Alembic raises its standard "Can't
locate revision" error from `command.upgrade` and the server refuses
to start — the safeguard against silently downgrading data. To
recover, either redeploy the version that wrote the newer
`alembic_version`, or hand-write a downgrade migration before
redeploying the older image.

### Local development

Alembic is invoked from `server/backend/`, so paths resolve relative
to it:

```
cd server/backend
CQ_DB_PATH=./dev.db uv run alembic current   # show current revision
CQ_DB_PATH=./dev.db uv run alembic upgrade head
```

The full environment-variable table for self-hosters lives in
[DEVELOPMENT.md](../DEVELOPMENT.md#self-hosted-server).

[issue-312]: https://github.com/mozilla-ai/cq/issues/312
[issue-310]: https://github.com/mozilla-ai/cq/issues/310

## Semantic search

Semantic similarity search is **disabled by default**. It activates only when
`TOKEN_EMBEDDING_URL` is set *and* the `semsearch` optional extra is installed.

### Installation

```bash
uv sync --extra semsearch
# or
pip install "cq-server[semsearch]"
```

The extra installs `sqlite-vec`, `numpy`, and `httpx`.

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TOKEN_EMBEDDING_URL` | to enable | — | Base URL of the [encoderfile](https://github.com/mozilla-ai/encoderfile) embedding service. When this variable is set and the `semsearch` extra is installed, every insert/update writes an embedding row and `query` modulates relevance by cosine distance. |
| `SEMSEARCH_EMBEDDING_DIM` | no | `768` | Dimensionality of the embedding vectors. **Must match the model served at `TOKEN_EMBEDDING_URL`.** |

### Embedding service contract

The server calls:

```
POST {TOKEN_EMBEDDING_URL}/predict
Content-Type: application/json

{"inputs": ["word1", "word2", ...]}
```

Expected response:

```json
{
  "results": [
    {
      "embeddings": [
        {"embedding": [0.1, 0.2, ...]},
        ...
      ]
    }
  ]
}
```

The server averages across all returned embeddings to produce a single vector.

### Disabled-by-default behaviour

When `TOKEN_EMBEDDING_URL` is unset (or the `semsearch` extra is not installed)
`semsearch.is_enabled()` returns `False` and all semsearch code-paths are
short-circuited; behaviour matches the non-semsearch baseline exactly.
