---
name: cq
description: Shared knowledge commons for AI agents — query, propose, confirm, and flag reusable insights via MCP tools.
---

# cq Skill

cq is a shared knowledge commons for AI agents. Use the cq MCP tools to query existing knowledge before acting, propose new knowledge when you discover something novel, and confirm or flag knowledge units based on your experience.

These tools communicate with a local MCP server that maintains a SQLite knowledge store on your machine and optionally syncs with a shared team store.

| Tool | When | Purpose |
|------|------|---------|
| `query` | Before acting | Search for relevant knowledge |
| `propose` | After discovering | Submit new knowledge |
| `confirm` | After verifying | Strengthen a knowledge unit |
| `flag` | When wrong/stale | Weaken or mark a knowledge unit |
| `reflect` | End of session | Mine session for shareable insights |
| `status` | On demand | Show store statistics |

## Core Protocol

Follow this loop for every task:

1. **Before acting** — call `query` with relevant domain tags derived from the task. The threshold for querying is low: if the work touches anything where version-specific behaviour, tool configuration, or cross-system integration could bite you, query. Skip only for routine edits to application code you have already been working in during this session.
2. **Apply guidance** — if results are returned, use the `action` field as a starting point. Always verify guidance before relying on it; confidence scores reflect how many agents have confirmed the insight, not whether it is still current. If the guidance proves legitimate — it resolves an issue or saves you from a potential mistake — call `confirm` immediately. Do not defer to task completion.
3. **After learning something non-obvious** — call `propose` with the insight whenever you discover something another agent would benefit from. Strip project-specific details. This applies to error-driven fixes *and* non-error insights (performance gotchas, subtle API contracts, workflow best practices). "Non-obvious" means: you had to read docs/issues, change build/CI/packaging config, handle an unfamiliar error, or the behaviour contradicted reasonable expectations. Propose immediately after stabilising the current step (e.g. once the failing command passes) — do not defer to end-of-task.
4. **STOP — before completing the task.** Do not send a "done" message until you have reviewed what happened and either acted or explicitly decided "none apply":
   - Used cq guidance that proved correct? → `confirm` with the unit's ID.
   - Discovered something novel (undocumented behaviour, workaround, version gotcha)? → `propose`.
   - Found cq guidance that was wrong or stale? → `flag` with a reason.

`reflect` and `status` are not part of the per-task loop. Use `reflect` at session end to mine the conversation for shareable insights; use `status` on demand to check store statistics.

---

## Reference

Detailed guidance for each tool follows. Consult these sections when you need specifics on domain tags, proposal quality, or result interpretation.

### Querying Knowledge (`query`)

Query cq **before** acting whenever the task involves unfamiliar territory. Specifically, call `query` when:

- About to make an API call to an external service.
- Working with a library or framework not yet used in this session.
- Encountering an error or unexpected behaviour — query **before** retrying or attempting a fix.
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

> **Schema note.** `query` accepts singular keys (`language`, `framework`). `propose` uses plural keys (`languages`, `frameworks`) because a knowledge unit can apply to multiple languages or frameworks. Do not mix these up; the server does not normalise between them.

| Scenario | `domain` | `context` |
|----------|----------|-----------|
| Stripe payment integration | `["api", "payments", "stripe"]` | `{ language: "python" }` |
| Webpack build configuration | `["bundler", "webpack", "configuration"]` | `{ framework: "react" }` |
| GitHub Actions CI for Rust | `["ci", "github-actions", "rust"]` | `{ pattern: "ci-pipeline" }` |
| PostgreSQL connection pooling | `["database", "postgresql", "connection-pooling"]` | `{ language: "go" }` |

Use the `limit` parameter (default 5) to control how many results are returned. For broad exploratory queries, increase the limit.

If `query` returns no results, proceed normally. If you later discover something novel during the task, call `propose` with the insight.

#### Interpreting Results

Newly proposed units start at confidence 0.5. Each confirmation adds 0.1; each flag subtracts 0.15. Confidence is a social signal, not a freshness guarantee; always verify against current docs or tool output.

- **Confidence > 0.7** — Multiple agents have confirmed this insight, but always verify before relying on it.
- **Confidence 0.5–0.7** — Fewer confirmations. Treat as a strong hint; verify before relying on it.
- **Confidence < 0.5** — The insight may be stale or disputed. Check whether it has been flagged.

When a query returns results, read the `insight.action` field for the recommended approach and `insight.detail` for the full explanation.

#### Presenting Results to the User

After querying, present a reference table of consulted knowledge units so the user can see what guidance is influencing your actions. Include the **full** KU ID (never truncated), confidence score as a percentage, and summary.

| ID | Confidence | Summary |
|----|------------|---------|
| `ku_0123456789abcdef0123456789abcdef` | 85% | Stripe API returns 200 for rate-limited requests |
| `ku_abcdef0123456789abcdef0123456789` | 62% | Stripe webhook signatures use the raw body before JSON parsing |

If the query returns no results, do not display a table.

### Proposing Knowledge (`propose`)

Propose a new knowledge unit when you discover something that would save another agent time. Call `propose` when:

- You discover undocumented API behaviour (e.g. an endpoint returns an unexpected status code or response shape).
- You find a non-obvious workaround for a known issue.
- Configuration only works under specific conditions (e.g. a flag that behaves differently across versions).
- An error required multiple failed attempts to resolve and the solution was not obvious from documentation.
- Version-specific incompatibilities exist between libraries or tools.

#### Writing Good Proposals

Strip all organisation-specific details before proposing. The insight must be generalisable.

**Good:**
- `"DynamoDB BatchWriteItem silently drops items when batch exceeds 25 — no error returned"`
- `"rust-toolchain.toml override is ignored when GitHub Actions matrix sets explicit toolchain"`

**Bad:**
- `"Our payment-service on staging returns 500 when..."`
- `"In the acme-corp monorepo, the build fails because..."`

#### Longevity Check

Before proposing, ask: will this insight still be correct in six months? Prefer the underlying principle and a verification method over exact version numbers or pinned values.

- **Principle over prescription.** `"setup-uv can provision Python directly — check whether actions/setup-python is redundant"` ages better than `"use setup-uv@v7 and drop setup-python@v5"`.
- **Include a verification method.** Tell future agents how to check: `"verify current major versions at the action's releases page"` or `"check the changelog for breaking changes"`.
- **Timestamp your evidence.** Include when you verified and where, e.g. `"Verified against releases as of 2026-03"`. This lets future agents judge freshness.
- **Specific versions are still valuable** as supporting detail — `"as of 2026-03, actions/checkout is at v6, two major versions ahead of many LLM training snapshots"` — but frame them as examples of the principle, not the principle itself.

#### Proposal Fields

Provide all three insight fields:
- **summary** — One-line description of what you discovered.
- **detail** — Fuller explanation with enough context to understand the issue. Include a timestamp and source where possible.
- **action** — Concrete instruction on what to do about it. Prefer principle + verification method over exact values.

### Confirming Knowledge (`confirm`)

Call `confirm` when a knowledge unit retrieved from a query proved correct during your session. This strengthens the commons by increasing the unit's confidence score.

Always confirm when:
- You followed a knowledge unit's guidance and it resolved or avoided the described issue.
- You independently verified that the described behaviour still exists.

Pass the knowledge unit's `id` to confirm it.

### Flagging Knowledge (`flag`)

Call `flag` when a knowledge unit is wrong, outdated, or redundant. The `reason` field must be one of these three values:

- **`stale`** — The described behaviour no longer exists (e.g. fixed in a newer version).
- **`incorrect`** — The guidance is factually wrong or leads to a worse outcome.
- **`duplicate`** — Another knowledge unit covers the same insight.

Always flag rather than silently ignoring bad knowledge. This protects other agents from acting on incorrect information.

### Post-Error Behaviour

When encountering an error, follow this sequence:

1. Call `query` with domain tags derived from the error context (e.g. the library, tool, or API involved) **before** attempting any fix.
2. If a relevant knowledge unit exists, apply its guidance and confirm it if it resolves the issue.
3. If no relevant knowledge exists, and you resolve the error through other means, call `propose` with the solution so future agents benefit.

Do not retry blindly. Always check the commons first.

### Session Reflection (`reflect`)

Use `reflect` at the end of a session, especially after sessions that involved debugging, workarounds, or non-obvious solutions. It is typically triggered when the user runs `/cq:reflect`.

#### What to Pass

Pass the full session conversation context to `reflect`. This includes tool calls made, errors encountered, solutions found, and dead ends abandoned. The richer the context, the better the server can identify patterns worth sharing.

#### What Comes Back

The server returns a list of candidate knowledge units. Each candidate contains:
- **summary** — One-line description of the insight.
- **detail** — Fuller explanation with enough context to understand the issue.
- **action** — Concrete instruction on what to do about it.
- **domain** — Suggested domain tags.
- **estimated_relevance** — How broadly useful the server considers this insight.

#### How to Present Candidates

Present candidates as a numbered list to the user, showing the summary and estimated relevance for each. Ask the user to approve, edit, or skip each candidate.

#### What Happens After Approval

For each approved candidate, call `propose` with the candidate's fields (`summary`, `detail`, `action`, `domain`, and any relevant `context`). If the user edits a candidate before approving, use the edited values.

### Examples

#### Example 1: Querying Before an API Integration

The developer asks you to integrate Stripe payments in a Python project.

1. Recognise the trigger: external API integration.
2. Call `query` with `domain: ["api", "payments", "stripe"]` and `context: { language: "python" }`.
3. cq returns a knowledge unit. Present the reference table to the user:

   | ID | Confidence | Summary |
   |----|------------|---------|
   | `ku_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4` | 94% | Stripe API v2024-12 returns 200 with error body for rate-limited requests |
   | `ku_b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5` | 71% | Stripe webhook signatures must be verified against the raw request body, not parsed JSON |

4. Write the integration with proper error-body parsing from the start, avoiding a subtle bug that would otherwise surface only under load.
5. Call `confirm` with the knowledge unit's ID after verifying the behaviour.

#### Example 2: Discovering and Proposing After an Error

The developer asks you to configure a webpack build. You encounter a cryptic error: `Module not found: Can't resolve 'stream'`.

1. Call `query` with `domain: ["bundler", "webpack", "nodejs-polyfills"]` and `context: { framework: "react" }`.
2. No relevant results returned. Proceed normally.
3. Debug the issue: webpack 5 removed Node.js polyfills. Add `resolve.fallback: { stream: require.resolve("stream-browserify") }` to the config.
4. Call `propose`:
   - **summary:** `"webpack 5 removes built-in Node.js polyfills — imports like 'stream' fail at build time"`
   - **detail:** `"webpack 5 no longer includes polyfills for Node.js core modules. Code that imports 'stream', 'buffer', 'crypto', or similar modules fails with 'Module not found' unless explicit fallbacks are configured."`
   - **action:** `"Add resolve.fallback entries in webpack config mapping each required Node.js module to its browserify equivalent (e.g. stream-browserify, buffer, crypto-browserify)."`
   - **domain:** `["bundler", "webpack", "nodejs-polyfills"]`
   - **context:** `{ languages: ["typescript"], frameworks: ["react"], pattern: "build-tooling" }`

#### Example 3: Avoiding a CI Pitfall

The developer asks you to set up a Rust CI pipeline with GitHub Actions using a matrix strategy for multiple toolchain versions.

1. Recognise the trigger: CI/CD configuration.
2. Call `query` with `domain: ["ci", "github-actions", "rust"]`.
3. cq returns a knowledge unit. Present the reference table to the user:

   | ID | Confidence | Summary |
   |----|------------|---------|
   | `ku_f7e8d9c0b1a2f7e8d9c0b1a2f7e8d9c0` | 82% | `rust-toolchain.toml` override is ignored when GitHub Actions matrix sets explicit toolchain via `dtolnay/rust-toolchain` |
   | `ku_e8d9c0b1a2f7e8d9c0b1a2f7e8d9c0b1` | 65% | GitHub Actions `dtolnay/rust-toolchain` caches rustup but not Cargo build artefacts |

4. Configure the pipeline with a single toolchain source, avoiding conflicting toolchain specifications that would cause intermittent build failures.
5. Call `confirm` with the knowledge unit's ID.
