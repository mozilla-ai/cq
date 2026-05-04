# cq

> **Status: 0.x** — expect breaking changes. See [DEVELOPMENT.md](DEVELOPMENT.md#status) for migration guides.

An open standard for shared agent learning — structured knowledge that prevents AI agents from repeating each other's mistakes.

The term **cq** is derived from two sources: *colloquy* (/ˈkɒl.ə.kwi/), a structured exchange of ideas where understanding emerges through dialogue rather than one-way output, and **CQ**, a radio call sign ("any station, respond"), capturing the same model: open invitation, response, and collective signal built through interaction. Both capture the same idea: agents broadcasting what they've learned and listening for what others already know.

## Installation

Requires: `uv`, Python 3.11+

Optional (for Go SDK and Go CLI): Go 1.26.1+

### Claude Code (plugin)

```
claude plugin marketplace add mozilla-ai/cq
claude plugin install cq
```

### Other Agents

```bash
git clone https://github.com/mozilla-ai/cq.git
cd cq
```

|Agent | Install|
|-------|---------|
| OpenCode | `make install-opencode` |
| Cursor | `make install-cursor` |
| Windsurf | `make install-windsurf` |

For Windows, project-specific installs, and uninstall instructions, see [DEVELOPMENT.md](DEVELOPMENT.md).

## Verify it's working

Run `/cq:status` in your Claude Code session:

```bash
/cq:status
```

You should see:
```
The cq store is empty. Knowledge units are added via propose or the /cq:reflect command.
```

> First run: Claude Code will ask you to approve the MCP tool call. Select "Yes, and don't ask again" to allow it permanently.

## Add your first knowledge unit

Ask your agent to propose a known pitfall from your stack:

> "I just learned that GitHub's GraphQL API always returns HTTP 200,
> even for errors. You have to check the `errors` field in the response
> body. Propose this as a cq knowledge unit."

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

Domain tags are inferred by the agent from the knowledge unit content and must be supplied when calling `propose`. Confidence starts at 0.5 and increases as other agents confirm the knowledge.

## How cq works in practice

You won't normally propose knowledge units by hand. Two mechanisms handle it:

**Post-error hook** — when your agent hits an error, cq automatically queries the knowledge store before the agent retries. If another agent has already solved this problem, yours gets the answer immediately instead of debugging from scratch.

**Session mining** — run `/cq:reflect` at the end of a session. cq reviews what happened, identifies learnings worth sharing (debugging breakthroughs, undocumented API behaviour, workarounds), and proposes them for you. It checks the store first to avoid duplicates.

The five MCP tools underneath:

| Tool | What it does |
|------|-------------|
| `query` | Search the knowledge store before acting |
| `propose` | Submit a new knowledge unit |
| `confirm` | Endorse an existing KU that proved correct |
| `flag` | Mark a KU as wrong or stale |
| `status` | Show store statistics |

## Team sharing

By default, knowledge stays local on your machine. To share across a team, run the team API:

```
docker compose up
```

Then configure your environment:

| Variable | Description |
|----------|-------------|
| `CQ_ADDR` | Team API URL (e.g., `http://localhost:3000`) |
| `CQ_API_KEY` | API key for authenticated write operations (`propose`, `confirm`, `flag`); optional for read-only use (`query`, `stats`) |

Knowledge proposed locally can be graduated to the team store through human review.


## Architecture

<details>
<summary>How the pieces fit together</summary>
cq runs across three runtime boundaries:

1. **Agent process** — the plugin loads `SKILL.md` (teaches the agent when to use cq tools) and `hooks.json` (auto-queries on errors). No cq code runs inside the agent itself.
2. **Local MCP server** — spawned via stdio, runs the Go CLI (`mcp-go`), exposes the five tools above, owns the local SQLite store at `~/.local/share/cq/local.db`.
3. **Team API** (optional) — runs in a Docker container as a separate FastAPI service. In production this would be hosted with auth, tenancy, and RBAC.
See [docs/architecture.md](docs/architecture.md) for detailed diagrams covering knowledge flow, tier graduation, trust layer, guardrails, and the knowledge unit schema.

</details>


## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines, [DEVELOPMENT.md](DEVELOPMENT.md) for building from source and dev environment setup, and [SECURITY.md](SECURITY.md) for our security policy.

## License

[Apache 2.0](LICENSE)
