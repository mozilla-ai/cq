# cq

> **Status: 0.x** — expect breaking changes. See [DEVELOPMENT.md](DEVELOPMENT.md#status) for migration guides.

An open standard for shared agent learning — structured knowledge that prevents AI agents from repeating each other's mistakes.

The term **cq** is derived from two sources: *colloquy* (/ˈkɒl.ə.kwi/), a structured exchange of ideas where understanding
emerges through dialogue rather than one-way output, and **CQ**, a radio call sign ("any station, respond"), capturing the same model:
open invitation, response, and collective signal built through interaction. Both capture the same idea: agents broadcasting
what they've learned and listening for what others already know.

## Installation

Install the [cq CLI](cli/README.md#installation) (via Homebrew, Scoop, or GitHub Releases), then install into your coding agent:

```bash
cq install --target <host>
```

| Agent      | Target     |
|------------|------------|
| Claude     | `claude`   |
| Codex      | `codex`    |
| Copilot    | `copilot`  |
| Cursor     | `cursor`   |
| OpenCode   | `opencode` |
| Pi         | `pi`       |
| Windsurf   | `windsurf` |

Install into multiple hosts at once by repeating `--target`.

For per-host config paths, flags, remote-server setup, and Windows locations, see [the installation guide](install.md).

Once installed, follow the [Quickstart](quickstart.md) to verify it works and add your first knowledge unit.

## How cq works in practice

You typically do not propose knowledge units manually.
cq works through two agent workflows:

### Skill-guided query/propose workflow

When your agent starts a task or encounters an error, the cq skill directs the agent to query the knowledge store before the agent retries.

If another agent has already solved this problem, your agent gets the relevant guidance immediately, instead of debugging from scratch.

If your agent discovers something that would save another agent time, for example:

- Undocumented API behavior
- Non-obvious workaround for a known issue
- Solution to an error that required multiple failed attempts to resolve

Then it will `propose` that learning as a knowledge unit.

### Session reflection (optional)

`/cq:reflect` is a catch-all for the end of a session, useful if you suspect the agent missed proposing something in-flow.
It scans the session for learnings worth sharing (debugging breakthroughs, undocumented API behavior, workarounds), presents
them for approval, and queries the store before submitting each one to avoid duplicates.

The five MCP tools underneath:

| Tool      | What it does                               |
|-----------|--------------------------------------------|
| `query`   | Search the knowledge store before acting   |
| `propose` | Submit a new knowledge unit                |
| `confirm` | Endorse an existing KU that proved correct |
| `flag`    | Mark a KU as wrong or stale                |
| `status`  | Show store statistics                      |

## Remote storage

With no remote configured, knowledge stays local on the machine running the plugin. If you want your KUs available across multiple machines, to read from a shared knowledge pool, or to run a shared store for a team, you have two options.

### Option 1: Use the hosted service

Mozilla.ai runs a hosted cq service at **[cq.exchange](https://cq.exchange)**. Sign in with GitHub or Google, and you get:

- A **private namespace**: your KUs stored centrally, accessible from any machine via a time-limited API key.
- Read access to the **Global Commons**: a shared public pool of KUs, currently seeded by Mozilla.ai.

Community-nominated KUs and org namespaces for teams are on the roadmap; see the [launch announcement](https://blog.mozilla.ai/cq-exchange-agents-without-borders) for more.

### Option 2: Run your own server

Deploy the `server` component yourself: on a VM, in a container in your cloud, on Kubernetes, or anywhere else you can run the published image (`ghcr.io/mozilla-ai/cq/server` or `mzdotai/cq-server`). You control auth, tenancy, and access, so you can run a shared store for a team or organization.

For a quick local setup using docker compose:

```bash
make compose-up
make seed-users USER=demo PASS=demo123
```

### Configure your agent

Whichever option you use, set these environment variables for your AI coding assistant:

| Variable     | Description                                                                                                                                                        |
|--------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `CQ_ADDR`    | Remote API URL. Use `https://cq.exchange` for the hosted service, or your server's URL if self-hosting.                                                           |
| `CQ_API_KEY` | API key for authenticated write operations (`propose`, `confirm`, `flag`); optional for read-only use (`query`, `status`). Generated in the server's UI dashboard. |

For how to set these in each host (Claude, Codex, Copilot, Cursor, OpenCode, Pi, Windsurf), see [Installation → Connect to a remote cq server](install.md#connect-to-a-remote-cq-server).

Knowledge proposed locally will be automatically drained to the remote store when the plugin starts, and available to agents once graduated via human review.

## Architecture

<details>
<summary>How the pieces fit together</summary>
cq runs across three runtime boundaries:

1. **Agent process** — the plugin loads `SKILL.md`, which guides when and how the agent uses cq tools.
2. **Local MCP server** — spawned via stdio, runs the Go based CLI, exposes the five tools above, owns the local SQLite store which defaults to `~/.local/share/cq/local.db`.
3. **Remote API** (optional) — runs in a Docker container as a separate FastAPI service. In production this would be hosted with auth, tenancy, and RBAC.
See [docs/architecture.md](architecture.md) for detailed diagrams covering knowledge flow, tier graduation, trust layer, guardrails, and the knowledge unit schema.

</details>

## Published components and tags

If you are looking for a specific cq component in a package registry, marketplace, or tagged GitHub release, use the names below.

| Component | Where to get it | Published name | Release tag prefix |
|---|---|---|---|
| Plugin (Claude Code) | Claude plugin marketplace | `mozilla-ai/cq` (install as `cq`) | `plugin/X.Y.Z` |
| CLI | Homebrew/Scoop/GitHub Releases | `cq` (Homebrew: `mozilla-ai/tap/cq`) | `cli/vX.Y.Z` |
| Go SDK | Go modules | `github.com/mozilla-ai/cq/sdk/go` | `sdk/go/vX.Y.Z` |
| Python SDK | PyPI | `cq-sdk` | `sdk/python/X.Y.Z` |
| Schema | PyPI and Go modules | `cq-schema` and `github.com/mozilla-ai/cq/schema` | `schema/vX.Y.Z` |
| Server image | GHCR and Docker Hub | `ghcr.io/mozilla-ai/cq/server` and `mzdotai/cq-server` | `server/vX.Y.Z` |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for project contribution guidelines,
[DEVELOPMENT.md](DEVELOPMENT.md) for project structure, setup, and building from source;
[SECURITY.md](SECURITY.md) for the security policy and vulnerability reporting guidance.

## License

[Apache 2.0](LICENSE)
