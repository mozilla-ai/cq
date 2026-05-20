# cq CLI

Command-line interface for [cq](https://github.com/mozilla-ai/cq) — the
shared agent knowledge commons. Also runs as an
[MCP](https://modelcontextprotocol.io/) server for IDE plugins and agent
frameworks.

## Installation

```bash
# Homebrew.
brew install --cask mozilla-ai/tap/cq

# Go install.
go install github.com/mozilla-ai/cq/cli@latest

# From source.
git clone https://github.com/mozilla-ai/cq.git
cd cq/cli
make build
```

## Usage

```bash
# Sign in interactively via your identity provider (control-plane).
cq auth providers
cq auth login github
cq auth status
cq auth logout

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

| Variable           | Description                        | Default                        |
|--------------------|------------------------------------|--------------------------------|
| `CQ_ADDR`          | Remote cq API address              | None (local-only)              |
| `CQ_API_KEY`       | API key (data-plane, long-lived)   | None                           |
| `CQ_LOCAL_DB_PATH` | Local SQLite path                  | `~/.local/share/cq/local.db`   |
| `CQ_CONFIG_DIR`    | Credential and config directory    | `${XDG_CONFIG_HOME:-~/.config}/cq` |
| `CQ_TIMEOUT`       | CLI operation timeout              | 30s                            |

## Authentication

`cq auth login [provider]` signs you in via your identity provider's OIDC flow. cq opens your default browser, completes the redirect on a short-lived loopback listener, and stores the resulting session JWT locally for use by control-plane commands.

```bash
# List the providers configured on the platform.
cq auth providers

# Sign in via the named provider.
cq auth login github

# Inspect the current sign-in state.
cq auth status

# Clear locally-stored credentials.
cq auth logout

# Revoke server session first, then clear local credentials.
cq auth logout --revoke

# Revoke all server sessions/devices, then clear local credentials.
cq auth logout --revoke --all-devices
```

`cq auth` requires `CQ_ADDR` (or `--addr`) for networked commands.

`cq auth logout` behavior:
- default: local-only credential cleanup
- `--revoke`: request server-side logout before local cleanup
- `--revoke --all-devices`: request logout across all devices

If server revocation fails (other than an already-invalid session), local credentials are kept so you can retry.

### Authentication vs API keys

cq separates two concerns:

- **`cq auth`** establishes an interactive *user* session via OIDC. The session JWT is short-lived and used for control-plane operations (creating API keys, managing your profile).
- **`CQ_API_KEY`** holds the long-lived *agent* credential used for data-plane operations (`propose`, `query`, `confirm`, `flag`). Set it directly for CI/CD and scripts; `cq auth` never stores or prints API keys.

### Credential storage

Session credentials are stored in your operating system's native credential store when reachable:

| Platform | Backend                    |
|----------|----------------------------|
| macOS    | Keychain                   |
| Linux    | Secret Service (D-Bus)     |
| Windows  | Credential Manager (DPAPI) |

When the OS keyring is unreachable (most commonly headless Linux without a running D-Bus session), cq falls back to a `chmod 600` JSON file at `${CQ_CONFIG_DIR}/credentials`.

> **macOS note:** the cq binary is currently distributed unsigned, so its Keychain entry is no more resistant to same-user processes than the file fallback would be. Stronger ACL-protected storage will land once code-signing infrastructure is in place.

## Knowledge tiers

Knowledge units live in one of three tiers:

- **local** — on-disk SQLite, never leaves your machine.
- **private** — stored on the remote at `CQ_ADDR`, visible to every client that can reach the same remote (e.g. teammates pointing at the same server).
- **public** — open commons; not yet available.

With `CQ_ADDR` set, `cq propose` sends the unit straight to the remote as `private` (falling back to local if the remote is unreachable). With no remote, everything stays local. `cq status` shows the count in each tier.

See the [top-level README](../README.md#knowledge-tiers) for the full description.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for build requirements and setup.

## License

[Apache-2.0](../LICENSE)
