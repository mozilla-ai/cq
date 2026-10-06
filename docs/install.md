# Install cq into your coding agent

`cq install` wires cq into a coding-agent host: it registers the cq MCP server (or, for hosts without MCP, a CLI mapping), installs the shared `cq` skill, and adds an always-loaded instruction so the agent knows to consult cq before starting work.

Re-running is idempotent, so it is safe to run again after an upgrade.

## Before you start

Install the `cq` CLI first — via Homebrew, Scoop, or a GitHub release. See the [CLI README](../cli/README.md#installation) for the options. The CLI must be on your `PATH`, because the installer writes its resolved path into each host's configuration.

## Quick start

```bash
cq install --target <host>
```

| Agent         | Target          |
|---------------|-----------------|
| Agent Skills  | `agent-skills`  |
| Claude        | `claude`        |
| Codex         | `codex`          |
| Copilot       | `copilot`        |
| Cursor        | `cursor`         |
| Devin Desktop | `devin-desktop`  |
| OpenCode      | `opencode`       |
| Pi            | `pi`             |

Install into several hosts at once by repeating `--target`:

```bash
cq install --target cursor --target opencode
```

| Flag          | Effect                                             |
|---------------|----------------------------------------------------|
| `--dry-run`   | Print the changes that would be made, without writing anything. |
| `--uninstall` | Remove cq from the selected hosts.                 |

For every host except Claude Code, the installer manages the host-specific configuration and installs the shared `cq` skill at `~/.agents/skills/cq/SKILL.md`. The `agent-skills` target is format-only: it installs the shared `cq` skill and a separate `cq-reflect` skill at `~/.agents/skills/cq-reflect/SKILL.md`. It does not configure MCP/tools or register a slash command; the host must discover `~/.agents/skills` and already provide cq tools. Agent Skills defines skill packaging and discovery, not slash-command discovery.

For the existing host targets, the installer also manages an MCP server entry (Pi instead receives a CLI mapping) and an always-loaded instruction where that host requires one.

Claude Code manages its own plugins, so `cq install --target claude` shells out to the Claude plugin marketplace rather than writing files.

`--uninstall` reverses host-specific configuration and instructions. It intentionally leaves the shared `cq` skill in place. The `agent-skills` target removes only its managed `cq-reflect` skill; each skill uses its own manifest so uninstalling or reinstalling another host does not remove it.

## Connect to a remote cq server
With no remote configured, knowledge stays local on the machine running the agent. To sync knowledge to a shared or hosted store, point the agent at a remote server with two environment variables:

| Variable     | Purpose                                                                 |
|--------------|-------------------------------------------------------------------------|
| `CQ_ADDR`    | Remote API URL. Use `https://cq.exchange` for the hosted service, `http://localhost:3000` for a local server, or your own server's URL if self-hosting. |
| `CQ_API_KEY` | API key for write operations (`propose`, `confirm`, `flag`). Optional for read-only use (`query`, `status`). Generated in the server's dashboard. |

See [Remote storage](../README.md#remote-storage) for choosing between the hosted service and running your own server.

> **The installer never writes these values.** `cq install` sets up the server entry, skill, and instructions, but it never writes `CQ_ADDR` or `CQ_API_KEY`. You add them yourself, to the entry the installer already created for your host — see the per-host **Point at a remote server** snippet in the next section. Keep the `command` and `args` the installer wrote; add only the environment block. In the examples, `/opt/homebrew/bin/cq` stands in for the path the installer detected — leave whatever path is already in your config.

## Per-host setup

Pick your host for the exact files `cq install` manages and how to point it at a remote server. Paths are shown for macOS and Linux; see [Windows](#windows) for Windows locations.

{% tabs %}

{% tab title="Agent Skills" %}
**Files managed**

| Asset | Location |
|-------|----------|
| Shared skill | `~/.agents/skills/cq/SKILL.md` |
| Reflection skill | `~/.agents/skills/cq-reflect/SKILL.md` |

Run `cq install --target agent-skills` to install these skills. This target does not set up a cq MCP server, CLI mapping, or host-specific command. Configure cq tools using the host's own setup, and ensure it discovers the shared Agent Skills directory. The skill can be invoked through the host's skill mechanism; slash-command names and discovery are host-specific and are not provided by the Agent Skills format.
{% endtab %}
{% tab title="Claude Code" %}
Installed through Claude Code's own plugin marketplace. `cq install --target claude` runs:

```bash
claude plugin marketplace add mozilla-ai/cq
claude plugin install cq
```

The `claude` CLI must be on your `PATH`. cq does not write Claude config files directly; the plugin is managed by Claude Code.

**Point at a remote server** — add a top-level `env` block to `~/.claude/settings.json`:

```json
{
  "env": {
    "CQ_ADDR": "https://cq.exchange",
    "CQ_API_KEY": "<your-api-key>"
  }
}
```
{% endtab %}

{% tab title="Codex" %}
**Files managed**

| Asset          | Location                        |
|----------------|---------------------------------|
| MCP server     | `~/.codex/config.toml` → `[mcp_servers.cq]` |
| Instruction    | `~/.codex/AGENTS.md` (cq block) |
| Skill          | `~/.agents/skills/cq/SKILL.md`  |

**Point at a remote server** — add an `env` table to the cq entry in `~/.codex/config.toml`:

```toml
[mcp_servers.cq.env]
CQ_ADDR = "https://cq.exchange"
CQ_API_KEY = "<your-api-key>"
```
{% endtab %}

{% tab title="Copilot (VS Code)" %}
**Files managed**

| Asset          | Location                        |
|----------------|---------------------------------|
| MCP server     | VS Code user `mcp.json` → `servers.cq` |
| Instruction    | `~/.copilot/instructions/cq.md` |
| Skill          | `~/.agents/skills/cq/SKILL.md`  |

The VS Code user `mcp.json` lives at:

- macOS: `~/Library/Application Support/Code/User/mcp.json`
- Linux: `~/.config/Code/User/mcp.json`
- Windows: `%APPDATA%\Code\User\mcp.json`

> **Default profile only.** The installer targets the default VS Code profile. Custom profiles (config under `profiles/<id>/`) and VS Code Insiders (`Code - Insiders`) need to be configured by hand.

**Point at a remote server** — add an `env` object to the cq entry:

```json
{
  "servers": {
    "cq": {
      "type": "stdio",
      "command": "/opt/homebrew/bin/cq",
      "args": ["mcp"],
      "env": {
        "CQ_ADDR": "https://cq.exchange",
        "CQ_API_KEY": "<your-api-key>"
      }
    }
  }
}
```
{% endtab %}

{% tab title="Cursor" %}
**Files managed**

| Asset            | Location                          |
|------------------|-----------------------------------|
| MCP server       | `~/.cursor/mcp.json` → `mcpServers.cq` |
| Rule             | `~/.cursor/rules/cq.mdc` (always applied) |
| Lifecycle hooks  | `~/.cursor/hooks.json`            |
| Skill            | `~/.agents/skills/cq/SKILL.md`    |

**Point at a remote server** — add an `env` object to the cq entry in `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "cq": {
      "command": "/opt/homebrew/bin/cq",
      "args": ["mcp"],
      "env": {
        "CQ_ADDR": "https://cq.exchange",
        "CQ_API_KEY": "<your-api-key>"
      }
    }
  }
}
```
{% endtab %}

{% tab title="Devin Desktop" %}
**Files managed**

| Asset          | Location                          |
|----------------|-----------------------------------|
| MCP server     | `~/.codeium/windsurf/mcp_config.json` → `mcpServers.cq` |
| Skill          | `~/.agents/skills/cq/SKILL.md`    |

> **Devin Desktop was formerly Windsurf.** After the rebrand it still reads MCP config from the original `~/.codeium/windsurf/` path, so the location below is unchanged.

**Point at a remote server** — add an `env` object to the cq entry in `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "cq": {
      "command": "/opt/homebrew/bin/cq",
      "args": ["mcp"],
      "env": {
        "CQ_ADDR": "https://cq.exchange",
        "CQ_API_KEY": "<your-api-key>"
      }
    }
  }
}
```
{% endtab %}

{% tab title="OpenCode" %}
**Files managed**

| Asset          | Location                          |
|----------------|-----------------------------------|
| MCP server     | `~/.config/opencode/opencode.json` → `mcp.cq` |
| Commands       | `~/.config/opencode/commands/`    |
| Instruction    | `~/.config/opencode/AGENTS.md` (cq block) |
| Skill          | `~/.agents/skills/cq/SKILL.md`    |

OpenCode does not honor `XDG_CONFIG_HOME`; set `OPENCODE_CONFIG_DIR` to install into a non-default config directory (see [Advanced](#advanced-install-environment-variables)).

**Point at a remote server** — OpenCode names the field `environment` (not `env`). Add it to the cq entry in `~/.config/opencode/opencode.json`:

```json
{
  "mcp": {
    "cq": {
      "environment": {
        "CQ_ADDR": "https://cq.exchange",
        "CQ_API_KEY": "<your-api-key>"
      }
    }
  }
}
```
{% endtab %}

{% tab title="Pi" %}
**Files managed**

| Asset          | Location                          |
|----------------|-----------------------------------|
| Instruction    | `~/.pi/agent/AGENTS.md` (cq block mapping each action to a CLI call) |
| Prompts        | `~/.pi/agent/prompts/`            |
| Skill          | `~/.agents/skills/cq/SKILL.md`    |

Pi has no native MCP support. Instead of an MCP server, the installed `AGENTS.md` block instructs the agent to run the `cq` CLI directly through its shell tool.

**Point at a remote server** — Pi has no MCP entry to carry the variables, so export them ahead of every shell command via `shellCommandPrefix` in `~/.pi/agent/settings.json`:

```json
{
  "shellCommandPrefix": "export CQ_ADDR='https://cq.exchange' CQ_API_KEY='<your-api-key>'"
}
```
{% endtab %}

{% endtabs %}

## Windows

Install the CLI via [Scoop](https://scoop.sh/):

```powershell
scoop install cq
```

Then run `cq install --target <host>` exactly as on macOS and Linux. Windows config locations differ from the paths shown above; for example, the VS Code user `mcp.json` is at `%APPDATA%\Code\User\mcp.json`.

## Advanced: install environment variables

These variables tune the installer itself and are not needed for a normal install.

| Variable             | Used by                          | Default                          | Purpose                                                            |
|----------------------|----------------------------------|----------------------------------|--------------------------------------------------------------------|
| `OPENCODE_CONFIG_DIR`| `cq install --target opencode`   | `~/.config/opencode`             | Install into a non-default OpenCode config directory.              |
| `CQ_INSTALL_BINARY`  | `cq install` (all targets)       | Auto-detected via the running binary | Override the `cq` path written into host config (for development and testing). |
