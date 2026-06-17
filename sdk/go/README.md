# cq Go SDK

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

| Variable           | Description           | Default                      |
|--------------------|-----------------------|------------------------------|
| `CQ_ADDR`          | Remote cq API address | None (local-only)            |
| `CQ_API_KEY`      | API key               | None                         |
| `CQ_LOCAL_DB_PATH` | Local SQLite path     | `~/.local/share/cq/local.db` |
| `CQ_LOCAL_DATABASE_URL` | Local store connection URL (e.g. `sqlite:///abs/path/local.db`) | None (falls back to `CQ_LOCAL_DB_PATH`) |

Or pass directly:

```go
c, err := cq.NewClient(
    cq.WithAddr("http://localhost:3000"),
    cq.WithLocalDBPath("~/.local/share/cq/local.db"),
)
```

The default database path follows the [XDG Base Directory spec](https://specifications.freedesktop.org/basedir/latest/).

### Custom storage

The local store is pluggable. By default the SDK opens a SQLite file at the path above; you can point it at a different backend or supply your own.

- **By connection string.** Set `CQ_LOCAL_DATABASE_URL` (for example `sqlite:///abs/path/local.db`); it takes precedence over `CQ_LOCAL_DB_PATH`. `cq.StoreFromURL` performs the same resolution programmatically.
- **By injection.** Pass any `cq.Store` to `cq.WithStore`:

  ```go
  c, err := cq.NewClient(cq.WithStore(cq.NewInMemoryStore()))
  ```

- **Bring your own.** Implement the `cq.Store` interface (`Unit`, `All`, `Insert`, `Update`, `Delete`, `Query`, `Stats`, `Close`) and inject it with `cq.WithStore`. Reuse the shared ranker `cq.RankCandidates` from your `Query`, and verify the implementation against the conformance suite in [`storetest`](./storetest).

Selection precedence: `WithStore` > `CQ_LOCAL_DATABASE_URL` > `CQ_LOCAL_DB_PATH`/`WithLocalDBPath` > XDG default. A first-party PostgreSQL adapter is planned as a separate module; until then a `postgres://` URL returns a clear error.

## Knowledge tiers

Every knowledge unit has a tier: `cq.Local` (on-disk SQLite, never leaves the machine), `cq.Private` (stored on the remote API at `CQ_ADDR`, visible to every client pointing at the same remote), or `cq.Public` (open commons; not yet available).

With a remote configured, `Propose` sends the unit to the remote and returns it tagged `cq.Private`; with no remote, or if the remote is unreachable, it writes the unit locally as `cq.Local`.

See the [top-level README](../../README.md#knowledge-tiers) for the full description.

## Storage Format

Knowledge units are stored as JSON in SQLite. The database schema is shared
with the [cq Python SDK](../../sdk/python/) — both SDKs read and write the
same `local.db` file. The [JSON Schema definitions](../../schema/) are the
source of truth.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for build requirements and setup.

## License

[Apache-2.0](../../LICENSE)
