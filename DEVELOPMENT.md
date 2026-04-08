# Development

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- [pnpm](https://pnpm.io/)
- Docker and Docker Compose

## Repository Structure

| Directory         | Component                              | Stack                              |
|-------------------|----------------------------------------|------------------------------------|
| `cli`             | CLI (with MCP server)                  | Go, Cobra, mcp-go                  |
| `sdk/go`          | Go SDK                                 | Go                                 |
| `sdk/python`      | Python SDK                             | Python                             |
| `plugins/cq`      | Agent plugin (skills, commands, hooks) | Markdown, Python                   |
| `scripts/install` | Multi-host installer                   | Python (stdlib only at runtime)    |
| `server`          | Remote knowledge server                | Python, FastAPI, TypeScript, React |

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

The remote API is available at `http://localhost:3000`.

For isolated component testing outside Docker, use `make dev-api` (remote API) and `make dev-ui` (dashboard).

## Agent Configuration

To point your agent at a local API instance, set `CQ_ADDR`.

### Claude Code

Add to `~/.claude/settings.json` under the `env` key:

```json
{
  "env": {
    "CQ_ADDR": "http://localhost:3000"
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
        "CQ_ADDR": "http://localhost:3000"
      }
    }
  }
}
```

`CQ_API_KEY` is documented in the README but not yet implemented (see [#63](https://github.com/mozilla-ai/cq/issues/63), [#80](https://github.com/mozilla-ai/cq/issues/80)).

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
| `make test` | Type checks and tests across plugin server and server backend |
