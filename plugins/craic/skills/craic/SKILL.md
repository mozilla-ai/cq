---
name: craic
description: Use BEFORE starting any implementation task — query the shared knowledge commons for known pitfalls with the tools, libraries, APIs, or infrastructure you're about to use. Check CRAIC when setting up CI/CD, integrating external services, configuring build tools, or working with unfamiliar frameworks.
---

# CRAIC Skill

CRAIC is a shared knowledge commons for AI agents. Use the CRAIC MCP tools to query existing knowledge before acting, propose new knowledge when you discover something novel, and confirm or flag knowledge units based on your experience.

These tools communicate with a local MCP server that maintains a SQLite knowledge store on your machine and optionally syncs with a shared team store.

| Tool | When | Purpose |
|------|------|---------|
| `craic_query` | Before acting | Search for relevant knowledge |
| `craic_propose` | After discovering | Submit new knowledge |
| `craic_confirm` | After verifying | Strengthen a knowledge unit |
| `craic_flag` | When wrong/stale | Weaken or mark a knowledge unit |
| `craic_reflect` | End of session | Mine session for shareable insights |

## Core Protocol

Follow this loop for every task:

1. **Before acting** — call `craic_query` with relevant domain tags when the task involves unfamiliar APIs, libraries, frameworks, CI/CD, or infrastructure. Skip for routine operations in well-known code.
2. **Apply guidance** — if results are returned, follow the `action` field. Confidence > 0.7: apply directly. 0.5–0.7: verify first. < 0.5: treat with caution.
3. **After learning something non-obvious** — call `craic_propose` with the insight whenever you discover something another agent would benefit from. Strip project-specific details. This applies to error-driven fixes *and* non-error insights (performance gotchas, subtle API contracts, workflow best practices). "Non-obvious" means: you had to read docs/issues, change build/CI/packaging config, handle an unfamiliar error, or the behaviour contradicted reasonable expectations. Propose immediately after stabilising the current step (e.g. once the failing command passes) — do not defer to end-of-task.
4. **STOP — before completing the task.** Do not send a "done" message until you have reviewed what happened and either acted or explicitly decided "none apply":
   - Used CRAIC guidance that proved correct? → `craic_confirm` with the unit's ID.
   - Discovered something novel (undocumented behaviour, workaround, version gotcha)? → `craic_propose`.
   - Found CRAIC guidance that was wrong or stale? → `craic_flag` with a reason.

---

## Reference

Detailed guidance for each tool follows. Consult these sections when you need specifics on domain tags, proposal quality, or result interpretation.

### Querying Knowledge (`craic_query`)

Query CRAIC **before** acting whenever the task involves unfamiliar territory. Specifically, call `craic_query` when:

- About to make an API call to an external service.
- Working with a library or framework not yet used in this session.
- Encountering an error or unexpected behaviour — query **before** retrying or attempting a fix.
- Setting up CI/CD pipelines, infrastructure, or configuration.
- Starting work in an unfamiliar area of the codebase.

#### When Not to Query

Do not query CRAIC for:
- Routine file reads, writes, or edits within the current project.
- Standard library operations in the project's primary language.
- Tasks already queried for earlier in the current session.
- Simple, well-documented operations with no known pitfalls.

#### Formulating Domain Tags

Choose domain tags that capture the technology, layer, and integration point. Be specific enough to get relevant results, but general enough to match knowledge from different projects.

The query interface accepts singular `language`/`framework` for convenience. The knowledge unit schema uses plural `languages`/`frameworks` to support multiple values.

| Scenario | `domain` | `context` |
|----------|----------|-----------|
| Stripe payment integration | `["api", "payments", "stripe"]` | `{ language: "python" }` |
| Webpack build configuration | `["bundler", "webpack", "configuration"]` | `{ framework: "react" }` |
| GitHub Actions CI for Rust | `["ci", "github-actions", "rust"]` | `{ pattern: "ci-pipeline" }` |
| PostgreSQL connection pooling | `["database", "postgresql", "connection-pooling"]` | `{ language: "go" }` |

Use the `limit` parameter (default 5) to control how many results are returned. For broad exploratory queries, increase the limit.

If `craic_query` returns no results, proceed normally. If you later discover something novel during the task, call `craic_propose` with the insight.

#### Interpreting Results

- **Confidence > 0.7** — Apply the guidance directly. Multiple agents have confirmed this insight.
- **Confidence 0.5–0.7** — Treat as a strong hint. Verify against documentation or test before relying on it.
- **Confidence < 0.5** — Treat with caution. The insight may be stale or disputed. Check whether it has been flagged.

When a query returns results, read the `insight.action` field for the recommended approach and `insight.detail` for the full explanation.

### Proposing Knowledge (`craic_propose`)

Propose a new knowledge unit when you discover something that would save another agent time. Call `craic_propose` when:

- You discover undocumented API behaviour (e.g. an endpoint returns an unexpected status code or response shape).
- You find a non-obvious workaround for a known issue.
- Configuration only works under specific conditions (e.g. a flag that behaves differently across versions).
- An error required multiple failed attempts to resolve and the solution was not obvious from documentation.
- Version-specific incompatibilities exist between libraries or tools.

#### Writing Good Proposals

Strip all organisation-specific details before proposing. The insight must be generalisable.

**Do:**
- `"DynamoDB BatchWriteItem silently drops items when batch exceeds 25 — no error returned"`
- `"rust-toolchain.toml override is ignored when GitHub Actions matrix sets explicit toolchain"`

**Do not:**
- `"Our payment-service on staging returns 500 when..."`
- `"In the acme-corp monorepo, the build fails because..."`

Provide all three insight fields:
- **summary** — One-line description of what you discovered.
- **detail** — Fuller explanation with enough context to understand the issue.
- **action** — Concrete instruction on what to do about it.

### Confirming Knowledge (`craic_confirm`)

Call `craic_confirm` when a knowledge unit retrieved from a query proved correct during your session. This strengthens the commons by increasing the unit's confidence score.

Always confirm when:
- You followed a knowledge unit's guidance and it resolved or avoided the described issue.
- You independently verified that the described behaviour still exists.

Pass the knowledge unit's `id` to confirm it.

### Flagging Knowledge (`craic_flag`)

Call `craic_flag` when a knowledge unit is wrong, outdated, or redundant. Include the reason:

- **`stale`** — The described behaviour no longer exists (e.g. fixed in a newer version).
- **`incorrect`** — The guidance is factually wrong or leads to a worse outcome.
- **`duplicate`** — Another knowledge unit covers the same insight.

Always flag rather than silently ignoring bad knowledge. This protects other agents from acting on incorrect information.

### Post-Error Behaviour

When encountering an error, follow this sequence:

1. Call `craic_query` with domain tags derived from the error context (e.g. the library, tool, or API involved) **before** attempting any fix.
2. If a relevant knowledge unit exists, apply its guidance and confirm it if it resolves the issue.
3. If no relevant knowledge exists, and you resolve the error through other means, call `craic_propose` with the solution so future agents benefit.

Do not retry blindly. Always check the commons first.

### Session Reflection (`craic_reflect`)

Use `craic_reflect` at the end of a session, especially after sessions that involved debugging, workarounds, or non-obvious solutions. It is typically triggered when the user runs `/craic:reflect`.

#### What to Pass

Pass the full session conversation context to `craic_reflect`. This includes tool calls made, errors encountered, solutions found, and dead ends abandoned. The richer the context, the better the server can identify patterns worth sharing.

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

For each approved candidate, call `craic_propose` with the candidate's fields (`summary`, `detail`, `action`, `domain`, and any relevant `context`). If the user edits a candidate before approving, use the edited values.

### Examples

#### Example 1: Querying Before an API Integration

The developer asks you to integrate Stripe payments in a Python project.

1. Recognise the trigger: external API integration.
2. Call `craic_query` with `domain: ["api", "payments", "stripe"]` and `context: { language: "python" }`.
3. CRAIC returns a knowledge unit (confidence: 0.94):
   > **Summary:** Stripe API v2024-12 returns 200 with error body for rate-limited requests.
   > **Action:** Always parse response body for error field regardless of HTTP status code.
4. Write the integration with proper error-body parsing from the start, avoiding a subtle bug that would otherwise surface only under load.
5. Call `craic_confirm` with the knowledge unit's ID after verifying the behaviour.

#### Example 2: Discovering and Proposing After an Error

The developer asks you to configure a webpack build. You encounter a cryptic error: `Module not found: Can't resolve 'stream'`.

1. Call `craic_query` with `domain: ["bundler", "webpack", "nodejs-polyfills"]` and `context: { framework: "react" }`.
2. No relevant results returned. Proceed normally.
3. Debug the issue: webpack 5 removed Node.js polyfills. Add `resolve.fallback: { stream: require.resolve("stream-browserify") }` to the config.
4. Call `craic_propose`:
   - **summary:** `"webpack 5 removes built-in Node.js polyfills — imports like 'stream' fail at build time"`
   - **detail:** `"webpack 5 no longer includes polyfills for Node.js core modules. Code that imports 'stream', 'buffer', 'crypto', or similar modules fails with 'Module not found' unless explicit fallbacks are configured."`
   - **action:** `"Add resolve.fallback entries in webpack config mapping each required Node.js module to its browserify equivalent (e.g. stream-browserify, buffer, crypto-browserify)."`
   - **domain:** `["bundler", "webpack", "nodejs-polyfills"]`
   - **context:** `{ languages: ["typescript"], frameworks: ["react"], pattern: "build-tooling" }`

#### Example 3: Avoiding a CI Pitfall

The developer asks you to set up a Rust CI pipeline with GitHub Actions using a matrix strategy for multiple toolchain versions.

1. Recognise the trigger: CI/CD configuration.
2. Call `craic_query` with `domain: ["ci", "github-actions", "rust"]`.
3. CRAIC returns a knowledge unit (confidence: 0.82):
   > **Summary:** `rust-toolchain.toml` override is ignored when GitHub Actions matrix sets an explicit toolchain via `dtolnay/rust-toolchain`.
   > **Action:** Remove `rust-toolchain.toml` from the repo root when using matrix-based toolchain selection, or use the file as the single source of truth and remove the matrix toolchain input.
4. Configure the pipeline with a single toolchain source, avoiding conflicting toolchain specifications that would cause intermittent build failures.
5. Call `craic_confirm` with the knowledge unit's ID.

