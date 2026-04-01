# cq

**cq** is derived from *colloquy* (/ˈkɒl.ə.kwi/), a structured exchange of ideas where understanding emerges through dialogue rather than one-way output. It reflects a focus on reciprocal knowledge sharing; systems that improve through participation, not passive use. In radio, **CQ** is a general call ("any station, respond"), capturing the same model: open invitation, response, and collective signal built through interaction.

Shared, experience-driven knowledge that prevents AI agents from repeating each other's mistakes.

An open standard for shared agent learning. Agents find, share, and confirm collective knowledge so they stop rediscovering the same failures independently.

## Installation

Requires: `uv`

Optional (for Go SDK and Go CLI): `go` 1.26+

### Claude Code (plugin)

```
claude plugin marketplace add mozilla-ai/cq
claude plugin install cq
```

Or from a cloned repo:

```bash
make install-claude
```

To uninstall:

```
claude plugin marketplace remove cq
```

Or from a cloned repo:

```bash
make uninstall-claude
```

If you configured team sync, you may also want to remove `CQ_TEAM_ADDR` and `CQ_TEAM_API_KEY` from `~/.claude/settings.json`.

### OpenCode (MCP server)

Also requires: `jq`

```bash
git clone https://github.com/mozilla-ai/cq.git
cd cq
make install-opencode
```

Or for a specific project:

```bash
make install-opencode PROJECT=/path/to/your/project
```

To uninstall:

```bash
make uninstall-opencode
# or for a specific project:
make uninstall-opencode PROJECT=/path/to/your/project
```

If you configured team sync, you may also want to remove the `environment` block from the cq entry in your OpenCode config.

### Go SDK

```bash
go get github.com/mozilla-ai/cq/sdk/go
```

```go
import cq "github.com/mozilla-ai/cq/sdk/go"

client, err := cq.NewClient()
if err != nil {
    panic(err)
}
defer client.Close()

result, err := client.Query(ctx, cq.QueryParams{Domains: []string{"api", "stripe"}})
if err != nil {
    panic(err)
}

_ = result.Units
```

### Go CLI

#### via Homebrew

```bash
brew install mozilla-ai/tap/cq
```

#### via GitHub Releases

Download the latest binary from the [releases page](https://github.com/mozilla-ai/cq/releases).

Or install with `curl`:

```bash
# CLI releases are tagged cli/vX.Y.Z.
VERSION="cli/v0.1.0"
OS="$(uname -s)"
ARCH="$(uname -m)"
curl -sSL "https://github.com/mozilla-ai/cq/releases/download/${VERSION}/cq_${OS}_${ARCH}.tar.gz" | tar xz cq
sudo mv cq /usr/local/bin/
```

> **macOS Gatekeeper:** If macOS blocks the binary, remove the quarantine flag:
> ```
> xattr -d com.apple.quarantine /usr/local/bin/cq
> ```

#### From Source

```bash
git clone https://github.com/mozilla-ai/cq.git
cd cq/cli
make build
./cq --help
```

## Configuration

cq works out of the box in **local-only mode** with no configuration. Set environment variables to customise the local store path or connect to a team API for shared knowledge.

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `CQ_LOCAL_DB_PATH` | No | `~/.local/share/cq/local.db` | Path to the local SQLite database (follows [XDG Base Directory spec](https://specifications.freedesktop.org/basedir/latest/); respects `$XDG_DATA_HOME`) |
| `CQ_TEAM_ADDR` | No | *(disabled)* | Team API URL. Set to enable team sync (e.g. `http://localhost:8742`) |
| `CQ_TEAM_API_KEY` | When team configured | — | API key for team API authentication |

When `CQ_TEAM_ADDR` is unset or empty, cq runs in local-only mode — knowledge stays on your machine. Set it to a team API URL to enable shared knowledge across your team.

### Claude Code

Add variables to `~/.claude/settings.json` under the `env` key:

```json
{
  "env": {
    "CQ_TEAM_ADDR": "http://localhost:8742",
    "CQ_TEAM_API_KEY": "your-api-key"  # pragma: allowlist secret
  }
}
```

### OpenCode

Add an `environment` key to the cq MCP server entry in your OpenCode config (`~/.config/opencode/opencode.json` or `<project>/.opencode/opencode.json`):

```json
{
  "mcp": {
    "cq": {
      "type": "local",
      "command": ["uv", "run", "--directory", "/path/to/cq/plugins/cq/server", "cq-mcp-server"],
      "environment": {
        "CQ_TEAM_ADDR": "http://localhost:8742",
        "CQ_TEAM_API_KEY": "your-api-key"  # pragma: allowlist secret
      }
    }
  }
}
```

Alternatively, export the variables in your shell before launching OpenCode.

## Architecture

cq runs across three runtime boundaries: the agent process (plugin configuration), a local MCP server (knowledge logic and private store), and a Docker container (team-shared API).

```mermaid
flowchart TB
    subgraph cc["Claude Code Process"]
        direction TB
        skill["SKILL.md\nBehavioural instructions"]
        hook["hooks.json\nPost-error auto-query"]
        cmd_status["/cq:status\nStore statistics"]
        cmd_reflect["/cq:reflect\nSession mining"]
    end

    subgraph mcp["Local MCP Server Process"]
        direction TB
        server["cq MCP Server\nPython / FastMCP"]
        local_db[("Local Store\n~/.local/share/cq/local.db\nSQLite")]
        server --> local_db
    end

    subgraph docker["Docker Container"]
        direction TB
        api["Team API\nPython / FastAPI\nlocalhost:8742"]
        team_db[("Team Store\n/data/team.db\nSQLite")]
        api --> team_db
    end

    cc <-->|"stdio / MCP protocol"| mcp
    mcp <-->|"HTTP / REST"| docker

    classDef ccStyle fill:#e8f0fe,stroke:#4285f4,color:#1a1a1a
    classDef mcpStyle fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a
    classDef dockerStyle fill:#e6f4ea,stroke:#34a853,color:#1a1a1a
    classDef dbStyle fill:#fce8e6,stroke:#ea4335,color:#1a1a1a

    class skill,hook,cmd_status,cmd_reflect ccStyle
    class server mcpStyle
    class api dockerStyle
    class local_db,team_db dbStyle
```

See [`docs/architecture.md`](docs/architecture.md) for the full set of architecture diagrams covering knowledge flow, tier graduation, plugin anatomy, and ecosystem integration.

## Status

Exploratory — this is a `0.x.x` project. Expect breaking changes to the database format and SDK interfaces before v1. We'll provide migration scripts where possible so your knowledge units survive upgrades.

See [`docs/`](docs/) for the proposal and PoC design.

### Migrating from earlier releases

The local SQLite database format changed during the 0.x cycle (enum values, field names, ID format). If you have knowledge units from an earlier version, run the migration script to bring them up to date:

```bash
# Local SDK database (auto-detects path).
./server/scripts/migrate-v1.sh

# Explicit path.
./server/scripts/migrate-v1.sh ~/.local/share/cq/local.db

# Team server running in a container.
docker compose exec cq-team-api bash /app/scripts/migrate-v1.sh
```

The script is idempotent — safe to run multiple times, on any 0.x database. It creates a backup before modifying anything. See the script header for full details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines, [DEVELOPMENT.md](DEVELOPMENT.md) for dev environment setup, and [SECURITY.md](SECURITY.md) for our security policy.

## License

Apache 2.0 — see [LICENSE](LICENSE).
