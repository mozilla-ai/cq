# cq CLI

Command-line interface for [cq](https://github.com/mozilla-ai/cq) — the
shared agent knowledge commons. Also runs as an
[MCP](https://modelcontextprotocol.io/) server for IDE plugins and agent
frameworks.

## Installation

```bash
# Go install.
go install github.com/mozilla-ai/cq/cli@latest

# From source.
git clone https://github.com/mozilla-ai/cq.git
cd cq/cli
make build
```

## Usage

```bash
# Search for relevant knowledge.
cq query --domain api --language go --format json

# Propose a new knowledge unit.
cq propose --domain api --domain go \
  --summary "Use retries for flaky APIs" \
  --detail "Exponential backoff with jitter prevents thundering herd." \
  --action "Wrap HTTP calls in a retry loop."

# Confirm a unit proved correct (boosts confidence by 10%).
cq confirm <unit_id>

# Flag a unit as problematic (reduces confidence by 15%).
cq flag <unit_id> --reason stale
cq flag <unit_id> --reason duplicate --duplicate-of <other_id>

# Show store status.
cq status
cq status --format json

# Print the agent protocol prompt (for frameworks without the cq plugin).
cq prompt

# Start the MCP server on stdio.
cq mcp
```

## Configuration

The CLI works out of the box in local-only mode with no configuration.

| Variable           | Description           | Default                      |
|--------------------|-----------------------|------------------------------|
| `CQ_TEAM_ADDR`    | Remote cq API address | None (local-only)            |
| `CQ_API_KEY`      | API key               | None                         |
| `CQ_LOCAL_DB_PATH` | Local SQLite path     | `~/.local/share/cq/local.db` |
| `CQ_TIMEOUT`      | CLI operation timeout | 30s                          |

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for build requirements and setup.

## License

[Apache-2.0](../LICENSE)
