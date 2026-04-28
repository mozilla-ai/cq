# Development

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- [pnpm](https://pnpm.io/)
- Docker and Docker Compose
- Go 1.26.1+ (only needed for Go SDK and CLI)

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

## Installing from Source

### Claude Code

```bash
make install-claude
```

To uninstall:

```bash
make uninstall-claude
```
If you configured remote sync, remove `CQ_ADDR` from `~/.claude/settings.json`.

### OpenCode

```bash
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
If you configured remote sync, remove the `environment` block from the cq entry in your OpenCode config.

OpenCode install requires `jq`.

### Cursor

```bash
make install-cursor
```

To uninstall:

```bash
make uninstall-cursor
# or for a specific project:
make uninstall-cursor PROJECT=/path/to/your/project
```

### Windsurf

Windsurf has no per-project MCP config, so only a global install is supported.

```bash
make install-windsurf
```

To uninstall:

```bash
make uninstall-windsurf
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

## Windows

Windows doesn't ship `make`, so the Makefile targets aren't available. Use the PowerShell wrapper instead:

```powershell
.\scripts\install.ps1 install --target cursor --global
.\scripts\install.ps1 install --target windsurf --global
.\scripts\install.ps1 install --target opencode --global
```

Or invoke the installer directly:

```powershell
cd scripts\install
uv run python -m cq_install install --target cursor --global
```

To uninstall, replace `install` with `uninstall`:

```powershell
.\scripts\install.ps1 uninstall --target cursor --global
```

### Config paths

Config paths are home-directory-relative, same as POSIX (`Path.home()` resolves to `%USERPROFILE%` on Windows):

| Host | Path |
|------|------|
| Cursor | `%USERPROFILE%\.cursor\mcp.json` |
| Windsurf | `%USERPROFILE%\.codeium\windsurf\mcp_config.json` |
| OpenCode | `%USERPROFILE%\.config\opencode\opencode.json` |
| Shared skills | 	`%USERPROFILE%\.agents\skills\cq\` |

### Python on PATH

The installer writes `python` (not `python3`) into the generated config on Windows. You need Python 3.11+ on PATH under that name for the MCP server to launch. The installer itself requires `uv`.

## Environment Variable Reference

### Installer and plugin bootstrap

These variables are used by the multi-host installer and plugin bootstrap runtime. Most users won't need to set any of them.

| Variable | Used by | Default | Purpose |
|----------|---------|---------|---------|
| `CLAUDE_PLUGIN_ROOT` | Claude plugin bootstrap | Script-relative path | Points bootstrap to the Claude-managed installed plugin root |
| `CQ_INSTALL_PLUGIN_ROOT` | Installer CLI | Auto-detected `plugins/cq` in repo | Dev/test override for resolving plugin source tree during installer runs |
| `OPENCODE_CONFIG_DIR` | Installer (OpenCode host) | `~/.config/opencode` | Overrides OpenCode global config target directory for install/uninstall |
| `XDG_DATA_HOME` | Installer + plugin bootstrap | `~/.local/share` | Base data directory for shared cq runtime assets (`$XDG_DATA_HOME/cq/runtime`) |

#### Windows-only fallbacks

| Variable | Default | Purpose |
|----------|---------|---------|
| `LOCALAPPDATA` | `%USERPROFILE%\AppData\Local` | Windows per-user fallback when `XDG_DATA_HOME` is unset |
| `APPDATA` | Used if `LOCALAPPDATA` unset | Secondary Windows fallback for shared runtime base directory |