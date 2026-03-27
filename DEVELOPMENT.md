# Development

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- [pnpm](https://pnpm.io/)
- Docker and Docker Compose
- jq (only needed for `make install-cursor` / `make install-opencode`)

## Repository Structure

| Directory | Component | Stack |
|-----------|-----------|-------|
| `plugins/cq/server` | MCP server (plugin) | Python, FastMCP |
| `team-api` | Team knowledge API | Python, FastAPI |
| `team-ui` | Review dashboard | TypeScript, React, Vite |

## Initial Setup

```bash
git clone https://github.com/mozilla-ai/cq.git
cd cq
make setup
```

## Running Locally

The quickest way to run everything is with Docker Compose.

Export the required secret first:

```bash
export CQ_JWT_SECRET=dev-secret
```

Start all services (runs in the foreground):

```bash
make compose-up
```

In a separate terminal, create a user and load sample knowledge units:

```bash
make seed-all USER=demo PASS=demo123
```

The team API is available at `http://localhost:8742`.

For isolated component testing outside Docker, use `make dev-api` (team API) and `make dev-ui` (dashboard).

## Agent Configuration

To point your agent at a local team API instance, set `CQ_TEAM_ADDR`.

### Claude Code

Add to `~/.claude/settings.json` under the `env` key:

```json
{
  "env": {
    "CQ_TEAM_ADDR": "http://localhost:8742"
  }
}
```

### Cursor

Add to `.cursor/mcp.json` (global `~/.cursor/mcp.json` or project-level), inside the cq server's `env` key:

```json
{
  "mcpServers": {
    "cq": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/cq/plugins/cq/server", "cq-mcp-server"],
      "env": {
        "CQ_TEAM_ADDR": "http://localhost:8742"
      }
    }
  }
}
```

### OpenCode

Add to `~/.config/opencode/opencode.json` or your project-level config, in the MCP server's `environment` key (not `env`):

```json
{
  "mcp": {
    "cq": {
      "environment": {
        "CQ_TEAM_ADDR": "http://localhost:8742"
      }
    }
  }
}
```

`CQ_TEAM_API_KEY` is documented in the README but not yet implemented (see [#63](https://github.com/mozilla-ai/cq/issues/63), [#80](https://github.com/mozilla-ai/cq/issues/80)).

## Docker Compose

| Command | Purpose |
|---------|---------|
| `make compose-up` | Build and start services |
| `make compose-down` | Stop services |
| `make compose-reset` | Stop services and wipe database |
| `make seed-users USER=demo PASS=demo123` | Create a user |
| `make seed-kus USER=demo PASS=demo123` | Load sample knowledge units |
| `make seed-all USER=demo PASS=demo123` | Create user and load sample KUs |

## Validation

| Command | Purpose |
|---------|---------|
| `make lint` | Format, lint, and type-check all components |
| `make test` | Type checks and tests across plugin server and team-api |
