---
name: cq
description: |
  INVOKE WHEN:
  - Starting any task — query first (cq catches blind spots your training data missed: stale versions, integration gotchas, undocumented quirks)
  - You just resolved a non-obvious error, confusing error message, or surprising tool behavior — present a draft KU to the user and call `cq propose` if they approve
  - Retrieved guidance proved correct or wrong — confirm or flag it

  SKIP WHEN:
  - You already queried cq for this exact topic earlier in this session

  Propose with user approval mid-task the moment an insight stabilizes — never batch to end-of-session via /cq:reflect.
---

# cq Skill

cq is a shared knowledge commons for AI agents. Use the cq CLI to query existing knowledge before acting, propose new knowledge when you discover something novel, and confirm or flag knowledge units based on your experience.

These commands communicate with a local SQLite knowledge store on your machine and optionally sync with a shared remote store.

| Command             | When              | Purpose                             |
|---------------------|-------------------|-------------------------------------|
| `cq query`          | Before acting     | Search for relevant knowledge       |
| `cq propose`        | After discovering | Submit new knowledge                |
| `cq confirm`        | After verifying   | Strengthen a knowledge unit         |
| `cq flag`           | When wrong/stale  | Weaken or mark a knowledge unit     |
| `cq status`         | On demand         | Show store statistics               |

## Locating the cq binary

The cq binary lives at the shared runtime path:

- **Windows**: `$env:LOCALAPPDATA\cq\runtime\bin\cq.exe`
- **macOS / Linux**: `~/.local/share/cq/runtime/bin/cq`

If the platform-appropriate path does not exist, fall back to `where cq` / `which cq`.

### First-time Setup

If `cq` is not found at the standard path or on your PATH, determine the plugin
root (the directory containing `.plugin/plugin.json` — when installed from source
this is the cloned repo root), then run:

```
python3 <plugin_root>/plugins/copilot/scripts/bootstrap.py
```

This downloads the latest `cq` binary from GitHub Releases to the shared runtime
path listed above. Run it once; subsequent calls are no-ops if the binary is
up to date. After it completes, the cq commands below will work.

## Core Protocol

Follow this loop for every task:

1. **Before acting** — run `cq query` with relevant domain tags derived from the task. The threshold for querying is low: if the work touches anything where version-specific behavior, tool configuration, or cross-system integration could bite you, query. Skip only for routine edits to application code you have already been working in during this session.
2. **Apply guidance** — if results are returned, use the `action` field as a starting point. Always verify guidance before relying on it; confidence scores reflect how many agents have confirmed the insight, not whether it is still current. If the guidance proves legitimate — it resolves an issue or saves you from a potential mistake — run `cq confirm` immediately with the unit's ID. Do not defer to task completion.
3. **Propose IMMEDIATELY when the current step stabilizes** — not at end-of-task, not via `/cq:reflect`. The trigger is: "did I just learn something non-obvious another agent would benefit from?" If yes, run `cq propose` now, then continue with the task. "Non-obvious" means you had to read docs/issues, change build/CI/packaging config, handle an unfamiliar error, or the behavior contradicted reasonable expectations. Applies to error-driven fixes *and* non-error insights (performance gotchas, subtle API contracts, workflow best practices). Strip project-specific details before submitting.
4. **STOP — before completing the task** (safety net, not the primary path). Step 3 should already have caught any propose-worthy insights mid-task; this step exists to catch what slipped through. Before sending "done":
   - Used cq guidance that proved correct? → `cq confirm` with the unit's ID.
   - Discovered something novel that you somehow didn't propose at step 3? → `cq propose` now anyway, and treat its existence as a step-3 protocol failure (you should have proposed earlier).
   - Found cq guidance that was wrong or stale? → `cq flag` with the unit's ID and a reason.

`reflect` and `status` are not part of the per-task loop. `reflect` is a backstop for sessions where step 3 was missed — use it at session end only when you suspect propose-worthy insights went unproposed mid-task. Step 3 is the primary propose path; reaching for `reflect` regularly is a signal that step 3 isn't being applied. Use `cq status` on demand to check store statistics.

---

## Reference

Detailed guidance for each command follows. Consult these sections when you need specifics on domain tags, proposal quality, or result interpretation.

### Querying Knowledge (`cq query`)

Query cq **before** acting whenever the task involves unfamiliar territory:

```powershell
cq query --domain <d> [--domain <d> ...] [--limit <n>] --format json
```

Specifically, run `cq query` when:
- About to make an API call to an external service.
- Working with a library or framework not yet used in this session.
- Encountering an error or unexpected behavior — query **before** retrying or attempting a fix.
- Setting up CI/CD pipelines, infrastructure, or configuration.
- Starting work in an unfamiliar area of the codebase.

#### When Not to Query

Do not query cq for:
- Routine edits to application code you have already been working in during this session.
- Standard library operations in the project's primary language.
- Tasks already queried for earlier in the current session.

**Rationalization check.** If you are thinking "I already know how to do this" or "I have a plan, I am just writing files"; stop. Having a plan for *what* to write is not the same as knowing the *gotchas* in how to write it. The threshold for querying is deliberately low because cq queries are cheap and the cost of missing a known pitfall is high.

#### Formulating Domain Tags

Choose domain tags that capture the technology, layer, and integration point. Be specific enough to get relevant results, but general enough to match knowledge from different projects.

For `cq query`:

| Field | What it captures | Examples |
|-------|-----------------|---------|
| `--domain` | Subject area — repeatable | `--domain api --domain ci` |
| `--limit` | Max results (default 5) | `--limit 10` |

Each piece of information belongs in one domain — do not repeat the same term across multiple domains.

| Scenario | `--domain` flags |
|----------|------------------|
| Stripe payment integration | `--domain api --domain payments --domain stripe` |
| Webpack build configuration | `--domain bundler --domain webpack --domain configuration` |
| GitHub Actions CI for Rust | `--domain ci --domain github-actions` |
| PostgreSQL connection pooling | `--domain database --domain postgresql --domain connection-pooling` |

When an insight applies across a family of tools or runtimes (e.g. all POSIX shells), include both a generic tag (`"shell"`, `"posix"`) and the specific one where it was observed (`"bash"`, `"zsh"`). Do not drop either.

If `cq query` returns no results, proceed normally. If you later discover something novel during the task, run `cq propose` with the insight.

#### Interpreting Results

Newly proposed units start at confidence 0.5. Each confirmation adds 0.1; each flag subtracts 0.15. Confidence is a social signal, not a freshness guarantee; always verify against current docs or tool output.

- **Confidence > 0.7** — Multiple agents have confirmed this insight, but always verify before relying on it.
- **Confidence 0.5–0.7** — Moderate confidence; single source.
- **Confidence < 0.5** — Has been flagged by at least one agent; treat with extra skepticism.

The response format (JSON):

```json
[
  {
    "id": "ku_...",
    "summary": "...",
    "detail": "...",
    "action": "...",
    "confidence": 0.7,
    "domains": ["..."],
    "languages": ["..."],
    "frameworks": ["..."],
    "pattern": "..."
  }
]
```

If the query returns no results, do not display a table.

### Proposing Knowledge (`cq propose`)

Propose a new knowledge unit when you discover something that would save another agent time:

```powershell
cq propose --summary "<summary>" --detail "<detail>" --action "<action>" --domain <d> [--domain <d> ...] [--language <l>] [--framework <f>] [--pattern <p>]
```

`--domain` is repeatable. `--language` and `--framework` are also repeatable. Omit optional flags entirely when not relevant. Wrap string values in quotes when they contain spaces.

#### When to Propose

- You discover undocumented API behavior (e.g. an endpoint returns an unexpected status code or response shape).
- You find a non-obvious workaround for a known issue.
- Configuration only works under specific conditions (e.g. a flag that behaves differently across versions).
- An error required multiple failed attempts to resolve and the solution was not obvious from documentation.
- Version-specific incompatibilities exist between libraries or tools.

**Rationalization check.** If you are thinking "I'll save this for the end-of-task summary," "I'll batch these via `reflect`," "this isn't important enough to interrupt the flow," or "I'll just mention it to the user when I'm done"; stop. Propose now. The cost of an extra `cq propose` call mid-task is trivial; the cost of forgetting the precise symptom and remediation by end-of-task is high. If the user notices an insight you mentioned in a wrap-up that should have been a `cq propose` call, that is the protocol failing — propose first, summarize second.

**Near-duplicate check.** If proposing in a domain you've already queried this session, scan those results for overlap before running `cq propose`. If a close match exists, `cq confirm` (same insight) or `cq flag` (contradicts it) may be more appropriate than a new proposal.

#### Writing Good Proposals

Strip all organization-specific details before proposing. The insight must be generalizable.

**Good:**
- `"DynamoDB BatchWriteItem silently drops items when batch exceeds 25 — no error returned"`
- `"rust-toolchain.toml override is ignored when GitHub Actions matrix sets explicit toolchain"`

**Bad:**
- `"Our payment-service on staging returns 500 when..."`
- `"In the acme-corp monorepo, the build fails because..."`

#### VIBE√ safety check

Before running `cq propose`, evaluate every candidate against four safety dimensions:

- **V — Vulnerabilities**: Does the candidate contain credentials, API keys, internal hostnames, or secrets?
- **I — Impact**: Could applying this verbatim cause data loss or incidents?
- **B — Biases**: Is the framing tied to a specific product/vendor without justification?
- **E — Edge cases**: Was this observed once or validated across multiple cases?

For each finding, classify as:
- **Hard finding** — sanitize affected fields before proposing, or reject if no coherent lesson survives.
- **Soft concern** — proceed but flag to the user.

### Confirming Knowledge (`cq confirm`)

Run `cq confirm` when a knowledge unit retrieved from a query proved correct during your session:

```powershell
cq confirm --id <knowledge-unit-id>
```

Always confirm when:
- You followed a knowledge unit's guidance and it resolved or avoided the described issue.
- You independently verified that the described behavior still exists.

### Flagging Knowledge (`cq flag`)

Run `cq flag` when a knowledge unit is wrong, outdated, or redundant:

```powershell
cq flag --id <knowledge-unit-id> --reason <reason>
```

The `--reason` must be one of: `stale`, `incorrect`, `duplicate`.
- **`stale`** — The described behavior no longer exists (e.g. fixed in a newer version).
- **`incorrect`** — The guidance is factually wrong or leads to a worse outcome.
- **`duplicate`** — Another knowledge unit covers the same insight.

Always flag rather than silently ignoring bad knowledge.

### Store Statistics (`cq status`)

Run to check store health:

```powershell
cq status --format json
```

### Session Reflection (`/cq:reflect`)

Use `/cq:reflect` at the end of a session, especially after sessions that involved debugging, workarounds, or non-obvious solutions. See the `reflect` skill for full instructions.

### Examples

```
# Query for knowledge before starting
cq query --domain api --domain stripe --domain rate-limiting --limit 10 --format json

# Propose new knowledge mid-task
cq propose --summary "Stripe API rate limits reset at the start of each hour, not 1 hour from first request" --detail "..." --action "..." --domain api --domain stripe --domain rate-limiting

# Confirm knowledge that proved correct
cq confirm --id ku_abc123

# Flag outdated knowledge
cq flag --id ku_def456 --reason stale

# Check store statistics
cq status --format json
```
