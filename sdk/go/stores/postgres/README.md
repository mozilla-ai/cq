# cq Go SDK — PostgreSQL Store Adapter

PostgreSQL-backed [`cq.Store`](../../README.md#store-interface) for the
[cq Go SDK](../../README.md). Lets multiple agents share a knowledge
base through a common Postgres instance instead of isolated SQLite files.

## Installation

```bash
go get github.com/mozilla-ai/cq/sdk/go/stores/postgres
```

This is a separate Go module so the pgx driver dependency stays off the
core SDK.

## Usage

```go
import (
    cq "github.com/mozilla-ai/cq/sdk/go"
    "github.com/mozilla-ai/cq/sdk/go/stores/postgres"
)

store, err := postgres.New("postgres://user:pass@localhost:5432/cq")
if err != nil {
    log.Fatal(err)
}
defer store.Close()

client, err := cq.NewClient(cq.WithStore(store))
```

The constructor validates the connection string, connects, pings the
server, and creates the schema tables if they do not exist.

## Schema

The adapter creates three tables on first connection:

| Table | Purpose |
|-------|---------|
| `knowledge_units` | Stores each unit as a JSONB document with an identity column for insertion ordering. |
| `knowledge_unit_domains` | Domain tag index for candidate selection during queries. |
| `metadata` | Writer stamp for cross-SDK diagnostics. |

## Query Strategy

Queries use domain-tag matching only (no full-text search). Candidates
whose domain tags overlap with the query are gathered, then ranked by
the shared `cq.RankCandidates` scorer. This matches the graceful
degradation the Store SPI allows when full-text is unavailable.

## Driver

Uses [pgx/v5](https://github.com/jackc/pgx) with connection pooling via
`pgxpool`. pgx is the actively maintained PostgreSQL driver for Go; the
older `lib/pq` is in maintenance mode and its own README recommends pgx.

## Development

```bash
make lint    # golangci-lint + license check + NOTICE freshness
make test    # unit tests (no Postgres required)
```

## License

[Apache-2.0](../../../../LICENSE)
