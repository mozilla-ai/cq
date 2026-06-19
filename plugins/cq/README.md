# cq Plugin

Agent plugin for [cq](https://github.com/mozilla-ai/cq) — the shared agent knowledge commons. Bundles the MCP server, the cq protocol skill, and session commands (`/cq:status`, `/cq:reflect`) so your coding agent can query, propose, confirm, and flag knowledge units during normal work.

The plugin works with Claude Code, OpenCode, Cursor, Windsurf, and Pi.

## Installation

Requires: the [cq CLI](../cli/README.md).

```bash
cq install --target claude
```

Supported targets: `claude`, `codex`, `copilot`, `cursor`, `opencode`, `pi`, `windsurf`. Install into multiple agents at once by repeating `--target`:

```bash
cq install --target claude --target cursor
```

Use `--project` to scope the install to a single project directory instead of globally:

```bash
cq install --target claude --project .
```

Preview what will change without writing anything:

```bash
cq install --target claude --dry-run
```

To remove:

```bash
cq install --target claude --uninstall
```

Re-running `cq install` is idempotent.

## What the plugin provides

The plugin bundles three things:

1. **MCP server** — exposes the five cq tools (`query`, `propose`, `confirm`, `flag`, `status`) over stdio via the `cq` binary.
2. **Skill** (`cq`) — the core protocol that guides the agent to query before acting, propose when it discovers something novel, and confirm or flag existing knowledge.
3. **Commands** — `/cq:status` and `/cq:reflect`, described below.

## MCP tools

| Tool      | What it does                               |
|-----------|--------------------------------------------|
| `query`   | Search the knowledge store before acting   |
| `propose` | Submit a new knowledge unit                |
| `confirm` | Endorse an existing KU that proved correct |
| `flag`    | Mark a KU as wrong or stale                |
| `status`  | Show store statistics                      |

The agent calls these tools during normal work. You do not need to invoke them directly.

## Commands

### `/cq:status`

Display a summary of the knowledge store: tier counts (local, private, public), recent local additions, confidence distribution, and domain breakdown.

### `/cq:reflect`

Mine the current session for knowledge worth sharing. The agent scans for debugging breakthroughs, undocumented API behavior, and workarounds, then presents candidates for your approval before proposing them to the store.

This is a catch-all for the end of a session; during normal work the skill guides the agent to propose knowledge inline as it discovers it.

## Configuration

The plugin uses the same environment variables as the CLI:

| Variable                | Description                        | Default                        |
|-------------------------|------------------------------------|--------------------------------|
| `CQ_ADDR`               | Remote cq API address              | None (local-only)              |
| `CQ_API_KEY`            | API key (data-plane, long-lived)   | None                           |
| `CQ_LOCAL_DATABASE_URL` | Local store connection URL (e.g. `sqlite:///abs/path/local.db`) | None (falls back to `CQ_LOCAL_DB_PATH`) |
| `CQ_LOCAL_DB_PATH`      | Local SQLite path                  | `~/.local/share/cq/local.db`   |
| `CQ_CONFIG_DIR`         | Credential and config directory    | `${XDG_CONFIG_HOME:-~/.config}/cq` |
| `CQ_TIMEOUT`            | Operation timeout                  | 30s                            |

Selection precedence: `CQ_LOCAL_DATABASE_URL` > `CQ_LOCAL_DB_PATH` > XDG default.

With no configuration, knowledge stays local on your machine. Set `CQ_ADDR` to connect to a remote store.

## Knowledge tiers

Knowledge units live in one of three tiers:

- **local** — on-disk SQLite, never leaves your machine.
- **private** — stored on the remote at `CQ_ADDR`, visible to every client that can reach the same remote (e.g. teammates pointing at the same server).
- **public** — open commons, available via [cq exchange](https://cq.exchange).

With `CQ_ADDR` set, `propose` sends the unit to the remote as `private` (falling back to local if the remote is unreachable). With no remote, everything stays local. `/cq:status` shows the count in each tier.

See the [top-level README](../../README.md) for the full description.

## License

[Apache-2.0](../../LICENSE)
