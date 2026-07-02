# cq Go SDK

{% hint style="info" icon="tag" %}
Version: v0.14.0
{% endhint %}

Go SDK for [cq](https://github.com/mozilla-ai/cq) — the shared agent
knowledge commons. It stores knowledge units locally in SQLite and
optionally syncs them remotely for shared learning.

## Installation

```bash
go get github.com/mozilla-ai/cq/sdk/go
```

## Quick Start

```go
import cq "github.com/mozilla-ai/cq/sdk/go"

// Create a client (auto-discovers config, falls back to local-only).
c, err := cq.NewClient()
if err != nil {
    log.Fatal(err)
}
defer c.Close()

// Query.
result, _ := c.Query(ctx, cq.QueryParams{
    Domains:   []string{"api", "stripe"},
    Languages: []string{"go"},
})

// Propose.
ku, _ := c.Propose(ctx, cq.ProposeParams{
    Summary: "Stripe 402 means card_declined",
    Detail:  "Check error.code, not error.type.",
    Action:  "Handle card_declined explicitly.",
    Domains: []string{"api", "stripe"},
})

// Confirm / flag.
c.Confirm(ctx, ku)
c.Flag(ctx, ku, cq.Stale)
c.Flag(ctx, ku, cq.Duplicate, cq.WithDuplicateOf("ku_..."))

// Get the canonical agent prompts.
import "github.com/mozilla-ai/cq/sdk/go/prompts"

skillPrompt := prompts.Skill()
reflectPrompt := prompts.Reflect()
```

## Configuration

The client works out of the box in local-only mode with no configuration.

| Variable              | Description                                                       | Default                       |
|-----------------------|-------------------------------------------------------------------|-------------------------------|
| `CQ_ADDR`             | Remote cq API address                                             | None (local-only)             |
| `CQ_API_KEY`          | API key for the remote API                                        | None                          |
| `CQ_LOCAL_DATABASE_URL` | Local store connection URL (e.g. `sqlite:///abs/path/local.db`) | None (falls back to `CQ_LOCAL_DB_PATH`) |
| `CQ_LOCAL_DB_PATH`    | Local SQLite file path                                            | `$XDG_DATA_HOME/cq/local.db` |
| `XDG_DATA_HOME`       | Base directory for the default database path ([XDG spec](https://specifications.freedesktop.org/basedir/latest/)) | `~/.local/share` |

Or pass directly:

```go
c, err := cq.NewClient(
    cq.WithAddr("http://localhost:3000"),
    cq.WithLocalDBPath("~/.local/share/cq/local.db"),
)
```

### Store interface

The local store is pluggable. The SDK defines a `Store` interface that the `Client` depends on; the default SQLite store satisfies it, and you can supply any implementation.

#### Selecting a store

The client resolves the local store in this precedence order:

1. **`cq.WithStore`** — inject any `cq.Store` directly.
2. **`CQ_LOCAL_DATABASE_URL`** — a connection-string URL resolved by `cq.StoreFromURL`. Accepted schemes: `sqlite:///abs/path` or `sqlite:path`. For `postgres://` URLs, use the [PostgreSQL adapter](https://github.com/mozilla-ai/cq/tree/docs/v0.2.0/sdk/go/stores/postgres) with `cq.WithStore`.
3. **`CQ_LOCAL_DB_PATH` / `cq.WithLocalDBPath`** — path to a SQLite file.
4. **XDG default** — `$XDG_DATA_HOME/cq/local.db` (typically `~/.local/share/cq/local.db`).

#### Interface

The `cq.Store` interface requires eight methods. Implementations must be safe for concurrent use.

| Method   | Signature                                            | Semantics |
|----------|------------------------------------------------------|-----------|
| `Unit`   | `(id string) (*KnowledgeUnit, error)`                | Retrieve by ID, or `nil` if absent. |
| `All`    | `() ([]KnowledgeUnit, error)`                        | Return every unit in the store. |
| `Insert` | `(ku KnowledgeUnit) error`                           | Insert a unit. Error on duplicate ID or empty domains after normalization. |
| `Update` | `(ku KnowledgeUnit) error`                           | Replace an existing unit. Error when the ID is absent or domains are empty. |
| `Delete` | `(id string) error`                                  | Remove by ID. Error when absent. |
| `Query`  | `(params QueryParams) (StoreQueryResult, error)`     | Return units matching the query, ranked most-relevant first. |
| `Stats`  | `(recentLimit int) (StoreStats, error)`              | Return aggregated store statistics. |
| `Close`  | `() error`                                           | Release resources. Must be safe to call more than once. |

#### Built-in implementations

- **SQLite store** (default, unexported) — opens a SQLite file with FTS5 full-text search, WAL journaling, and domain-tag indexing.
- **[PostgreSQL adapter](https://github.com/mozilla-ai/cq/tree/docs/v0.2.0/sdk/go/stores/postgres)** — separate module (`github.com/mozilla-ai/cq/sdk/go/stores/postgres`). Connects to a shared PostgreSQL instance for multi-agent knowledge sharing. Domain-tag matching only (no full-text).
- **`NewInMemoryStore()`** — map-backed, no persistence. Useful for tests and as a worked example for custom stores (domain-tag matching only, no full-text).

```go
c, err := cq.NewClient(cq.WithStore(cq.NewInMemoryStore()))
```

PostgreSQL:

```go
import "github.com/mozilla-ai/cq/sdk/go/stores/postgres"

store, err := postgres.New(context.Background(), "postgres://user:pass@localhost:5432/cq")
c, err := cq.NewClient(cq.WithStore(store))
```

#### Bring your own

Implement the `cq.Store` interface and inject it with `cq.WithStore`. Reuse the shared ranker `cq.RankCandidates` from your `Query` implementation so ranking stays consistent across backends. Verify the implementation against the conformance suite in [`storetest`](https://github.com/mozilla-ai/cq/tree/docs/v0.2.0/sdk/go/storetest):

```go
import "github.com/mozilla-ai/cq/sdk/go/storetest"

func TestMyStore(t *testing.T) {
    storetest.RunConformance(t, func() cq.Store {
        return NewMyCustomStore()
    })
}
```

## Knowledge tiers

Every knowledge unit has a tier: `cq.Local` (on-disk SQLite, never leaves the machine), `cq.Private` (stored on the remote API at `CQ_ADDR`, visible to every client pointing at the same remote), or `cq.Public` (open commons; not yet available).

With a remote configured, `Propose` sends the unit to the remote and returns it tagged `cq.Private`; with no remote, or if the remote is unreachable, it writes the unit locally as `cq.Local`.

See the [top-level README](../../index.md) for the full description.

## Storage Format

Knowledge units are stored as JSON in SQLite. The database schema is shared
with the [cq Python SDK](../python/README.md) — both SDKs read and write the
same `local.db` file. The [JSON Schema definitions](https://github.com/mozilla-ai/cq/tree/docs/v0.2.0/schema) are the
source of truth.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for build requirements and setup.

## License

[Apache-2.0](../../LICENSE)
