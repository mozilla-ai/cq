# cq

> **Status: 0.x** — expect breaking changes. See [DEVELOPMENT.md](DEVELOPMENT.md#status) for migration guides.

An open standard for shared agent learning — structured knowledge that prevents AI agents from repeating each other's mistakes.

The term **cq** is derived from two sources: *colloquy* (/ˈkɒl.ə.kwi/), a structured exchange of ideas where understanding
emerges through dialogue rather than one-way output, and **CQ**, a radio call sign ("any station, respond"), capturing the same model:
open invitation, response, and collective signal built through interaction. Both capture the same idea: agents broadcasting
what they've learned and listening for what others already know.

## Published components and tags

If you are looking for a specific cq component in a package registry, marketplace, or tagged GitHub release, use the names below.

| Component            | Where to get it           | Published name                                         | Release tag prefix |
|----------------------|---------------------------|--------------------------------------------------------|--------------------|
| Plugin (Claude Code) | Claude plugin marketplace | `mozilla-ai/cq` (install as `cq`)                      | N/A                |
| CLI                  | Homebrew/GitHub Releases  | `github.com/mozilla-ai/cq/cli`                         | `cli/vX.Y.Z`       |
| Go SDK               | Go modules                | `github.com/mozilla-ai/cq/sdk/go`                      | `sdk/go/vX.Y.Z`    |
| Python SDK           | PyPI                      | `cq-sdk`                                               | `sdk/python/X.Y.Z` |
| Schema               | PyPI and Go modules       | `cq-schema` and `github.com/mozilla-ai/cq/schema`      | `schema/vX.Y.Z`    |
| Server image         | GHCR and Docker Hub       | `ghcr.io/mozilla-ai/cq/server` and `mzdotai/cq-server` | `server/vX.Y.Z`    |

## Plugin Installation

Requires: `uv`, Python 3.11+

Optional (for Go SDK and Go CLI): Go 1.26.1+

### Claude Code (plugin)

```bash
claude plugin marketplace add mozilla-ai/cq
claude plugin install cq
```

### Other Agents

```bash
git clone https://github.com/mozilla-ai/cq.git
cd cq
```

Run `make setup-plugin` before running the relevant `Makefile` target:

| Agent    | Install                 |
|----------|-------------------------|
| OpenCode | `make install-opencode` |
| Cursor   | `make install-cursor`   |
| Windsurf | `make install-windsurf` |

For Windows, project-specific installs, and uninstall instructions, see [DEVELOPMENT.md](DEVELOPMENT.md).

## Verify the plugin is working

Run `/cq:status` in your AI coding agent's terminal session:

```bash
/cq:status
```

You should see:
```
The cq store is empty. Knowledge units are added via propose or the /cq:reflect command.
```

> First run: Your AI coding agent will ask you to approve the MCP tool call. Select "Yes, and don't ask again" to allow it permanently.

## Add your first knowledge unit

Ask your AI coding agent to propose a known pitfall from your stack:

> "I just learned that GitHub's GraphQL API always returns HTTP 200,
> even for errors. You have to check the `errors` field in the response
> body. Verify this and propose this as a cq knowledge unit."

The agent calls `cq:propose` with structured fields — a summary, detail,
recommended action, and domain tags — and you'll see something like:

```
Stored: ku_7c67fc4bb4db46698eb2d85ed92b43a7 — "GitHub's GraphQL API always returns HTTP 200, even for errors — check the errors field in the response body to detect failures."
```

## Check your store

Run `/cq:status` again:
```
cq Knowledge Store

Tier Counts
local: 1

Domains
api: 1 | error-handling: 1 | github: 1 | graphql: 1

Recent Local Additions
- ku_121710dc2bbf41949b4df2a78c7e3b7a: "GitHub's GraphQL API always returns HTTP 200,
  even for errors — check the errors field in the response body, not just the status code." (today)

Confidence Distribution
■ 0.5-0.7: 1 unit
```

Domain tags are inferred by the agent from the knowledge unit content and must be supplied when calling `propose`.
Confidence starts at 0.5 and increases as other agents confirm the knowledge.

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

### Session reflection workflow

Run `/cq:reflect` at the end of a session. cq reviews what happened, identifies learnings worth sharing
(debugging breakthroughs, undocumented API behaviour, workarounds), and proposes them for you.
It checks the store first to avoid duplicates.

The five MCP tools underneath:

| Tool      | What it does                               |
|-----------|--------------------------------------------|
| `query`   | Search the knowledge store before acting   |
| `propose` | Submit a new knowledge unit                |
| `confirm` | Endorse an existing KU that proved correct |
| `flag`    | Mark a KU as wrong or stale                |
| `status`  | Show store statistics                      |

## Team sharing

By default, knowledge stays local on your machine.

To share knowledge units across remote agents, machines, or a team, run the `server` component which uses values from the `.env` file:

```bash
make compose-up
```

Create a user:

```bash
make seed-users USER=demo PASS=demo123
```

Then configure the required environment variables for the AI coding assistant:

| Variable     | Description                                                                                                                                                                          |
|--------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `CQ_ADDR`    | Remote API URL (e.g., `http://localhost:3000`)                                                                                                                                       |
| `CQ_API_KEY` | API key for authenticated write operations (`propose`, `confirm`, `flag`); optional for read-only use (`query`, `stats`). This can be generated in the remote server's UI dashboard. |

Knowledge proposed locally will be automatically drained to the remote store when the plugin starts, and available to agents once graduated via human review.

## Architecture

<details>
<summary>How the pieces fit together</summary>
cq runs across three runtime boundaries:

1. **Agent process** — the plugin loads `SKILL.md`, which guides when and how the agent uses cq tools.
2. **Local MCP server** — spawned via stdio, runs the Go based CLI (`mcp-go`), exposes the five tools above, owns the local SQLite store which defaults to `~/.local/share/cq/local.db`.
3. **Remote API** (optional) — runs in a Docker container as a separate FastAPI service. In production this would be hosted with auth, tenancy, and RBAC.
See [docs/architecture.md](docs/architecture.md) for detailed diagrams covering knowledge flow, tier graduation, trust layer, guardrails, and the knowledge unit schema.

</details>


## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for project contribution guidelines,
[DEVELOPMENT.md](DEVELOPMENT.md) for project structure, setup, and building from source;
[SECURITY.md](SECURITY.md) for the security policy and vulnerability reporting guidance.

## License

[Apache 2.0](LICENSE)
