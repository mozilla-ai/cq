# Development

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- [pnpm](https://pnpm.io/)
- Docker and Docker Compose
- Go 1.26.1+ (CLI, Go SDK)

## Repository Structure

| Directory         | Component                              | Stack                              |
|-------------------|----------------------------------------|------------------------------------|
| `cli`             | CLI (with MCP server)                  | Go, Cobra, mcp-go                  |
| `sdk/go`          | Go SDK                                 | Go                                 |
| `sdk/python`      | Python SDK                             | Python                             |
| `plugins/cq`      | Agent plugin (skills, commands, hooks) | Markdown, Python                   |
| `schema`          | JSON Schema definitions                | JSON Schema, Python                |
| `server`          | Remote knowledge server                | Python, FastAPI, TypeScript, React |

## Initial Setup

```bash
git clone https://github.com/mozilla-ai/cq.git
cd cq
make setup
```

## Installing into a Coding Agent

All hosts are installed via the `cq` CLI binary:

```bash
cq install --target <host>
```

Supported hosts: `claude`, `codex`, `copilot`, `cursor`, `opencode`, `pi`, `windsurf`.

Install into multiple hosts at once by repeating `--target`:

```bash
cq install --target cursor --target opencode
```

Preview what will change without writing anything:

```bash
cq install --target cursor --dry-run
```

To remove:

```bash
cq install --target cursor --uninstall
```

Re-running `cq install` is idempotent.

### Go SDK

```bash
go get github.com/mozilla-ai/cq/sdk/go
```

### Go CLI

See [`cli/README.md`](cli/README.md) for Homebrew, GitHub Releases, and from-source install instructions.

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

### Pi

Add to `~/.pi/agent/settings.json` under `shellCommandPrefix`:

```json
{
  "shellCommandPrefix": "export CQ_ADDR='http://localhost:3000'"
}
```

## Configuration

cq works out of the box in local-only mode with no configuration. Set environment variables to customize the local store path or connect to a remote API.

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `CQ_LOCAL_DB_PATH` | No | `~/.local/share/cq/local.db` | Path to the local SQLite database (follows [XDG Base Directory spec](https://specifications.freedesktop.org/basedir/latest/); respects `$XDG_DATA_HOME`) |
| `CQ_ADDR` | No | *(disabled)* | Remote API URL. Set to enable remote sync (e.g. `http://localhost:3000`) |
| `CQ_API_KEY` | When remote configured | — | API key for remote API write operations (`propose`, `confirm`, `flag`) |

### Self-hosted server

Running the server (see `server/`) requires:

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `CQ_JWT_SECRET` | Yes | — | Secret used to sign JWTs issued by `/auth/login`. |
| `CQ_API_KEY_PEPPER` | Yes | — | Server-side pepper combined with each API key under HMAC-SHA256. |
| `CQ_DATABASE_URL` | No | — | SQLAlchemy URL for the backing database. Currently only `sqlite:///<path>` is supported; `postgresql+psycopg://...` is reserved for the upcoming PostgreSQL backend ([epic #257](https://github.com/mozilla-ai/cq/issues/257)) and rejected at startup. |
| `CQ_DB_PATH` | No | `/data/cq.db` | Shortcut for SQLite deployments — wrapped as `sqlite:///<path>` internally. Used when `CQ_DATABASE_URL` is unset. |
| `CQ_PORT` | No | `3000` | HTTP listen port. |

API keys are created per user from the web UI: log in, open **API Keys**, give the key a name, choose a TTL, and copy the plaintext token when it is shown. The token is displayed exactly once. Set it as `CQ_API_KEY` on each client (plugin, SDK, CLI) that should authenticate against this server.

The data-plane write routes require a valid API key:

— `POST /api/v1/knowledge`
- `POST /api/v1/knowledge/{id}/confirmations`
- `POST /api/v1/knowledge/{id}/flags`

Data-plane reads remain open:

- `GET /api/v1/knowledge`
- `GET /api/v1/knowledge/stats`
- `GET /api/v1/health`

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

## Status

Exploratory — this is a `0.x.x` project. Expect breaking changes to the database format and SDK interfaces before v1. We'll provide migration scripts where possible so your knowledge units survive upgrades.

See the [proposal](CQ-Proposal.md) and [architecture overview](architecture.md) for the design.

### Migrating from earlier releases

The local SQLite database format changed during the 0.x cycle (enum values, field names, ID format). If you have knowledge units from an earlier version, run the migration script to bring them up to date:

```bash
# Local SDK database (auto-detects path).
./server/scripts/migrate-v1.sh

# Explicit path.
./server/scripts/migrate-v1.sh ~/.local/share/cq/local.db

# Remote server running in a container.
docker compose exec cq-server bash /app/scripts/migrate-v1.sh
```

The script is idempotent — safe to run multiple times, on any 0.x database. It creates a backup before modifying anything. See the script header for full details.

## Windows

Install the cq binary via [Scoop](https://scoop.sh/):

```powershell
scoop install cq
```

Then use `cq install --target <host>` the same as on macOS/Linux.

## Environment Variable Reference

### Install

| Variable | Used by | Default | Purpose |
|----------|---------|---------|---------|
| `OPENCODE_CONFIG_DIR` | `cq install --target opencode` | `~/.config/opencode` | Overrides OpenCode global config target directory |
| `CQ_INSTALL_BINARY` | `cq install` (all targets) | Auto-detected via `os.Executable()` | Dev/test override for the binary path written into host config |
