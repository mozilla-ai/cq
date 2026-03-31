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

// Get the canonical agent protocol prompt.
prompt := c.Prompt()
```

## Configuration

The client works out of the box in local-only mode with no configuration.

| Variable           | Description           | Default                      |
|--------------------|-----------------------|------------------------------|
| `CQ_TEAM_ADDR`    | Remote cq API address | None (local-only)            |
| `CQ_API_KEY`      | API key               | None                         |
| `CQ_LOCAL_DB_PATH` | Local SQLite path     | `~/.local/share/cq/local.db` |

Or pass directly:

```go
c, err := cq.NewClient(
    cq.WithAddr("http://localhost:8742"),
    cq.WithLocalDBPath("~/.local/share/cq/local.db"),
)
```

The default database path follows the [XDG Base Directory spec](https://specifications.freedesktop.org/basedir/latest/).

## Storage Format

Knowledge units are stored as JSON in SQLite. The database schema is shared
with the [cq Python SDK](../../sdk/python/) — both SDKs read and write the
same `local.db` file. The [JSON Schema definitions](../../schema/) are the
source of truth.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for build requirements and setup.

## License

[Apache-2.0](../../LICENSE)
