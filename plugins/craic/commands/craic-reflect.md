---
name: craic:reflect
description: Mine the current session for knowledge worth sharing — identify learnings, present them for approval, and propose each approved candidate to the CRAIC knowledge store.
---

# /craic:reflect

Retrospectively mine this session for shareable knowledge units and submit approved candidates to CRAIC.

## Instructions

### Step 1 — Summarise the session context

Before calling any tool, construct a compact session summary covering:

- External APIs, libraries, or frameworks used.
- Errors encountered and how each was resolved.
- Workarounds applied for known or unexpected issues.
- Configuration decisions that only work under specific conditions.
- Tool calls that failed before the correct approach was found.
- Any behaviour observed that differed from documentation or expectation.
- Dead ends abandoned and why.

The summary should be dense prose — enough for a reader with no prior context to reconstruct the session's technical events. Omit routine file edits, standard library calls, and anything already well-documented.

### Step 2 — Call `craic_reflect`

Call the `craic_reflect` MCP tool, passing the session summary as `session_context`.

```
craic_reflect(session_context="<your session summary>")
```

The tool may return a `candidates` list or may return an empty list with `status: "stub"`. In both cases, proceed to Step 3.

If the tool call fails (MCP server unavailable, timeout, or any error), note this briefly to the user and continue to Step 3 using local reasoning only — the reflect flow does not require the tool to succeed.

### Step 3 — Identify candidate knowledge units

Using your own reasoning, scan the session for insights worth sharing. Use any candidates returned by `craic_reflect` as a starting point; if none were returned, identify candidates independently.

A candidate is worth sharing if it meets **all** of these criteria:

1. **Generalisable** — applies beyond this project, team, or codebase. Strip all organisation-specific names, internal service names, and proprietary identifiers.
2. **Non-obvious** — not directly stated in official documentation, or contradicts documentation.
3. **Actionable** — another agent could apply it immediately with a concrete change.
4. **Novel** — unlikely to already exist in the commons (err toward including, not excluding).

Look specifically for:

- **Undocumented API behaviour** — an endpoint returned an unexpected status code, response shape, or side effect.
- **Workarounds for known issues** — a library or tool required a non-standard setup to function correctly.
- **Condition-specific configuration** — a setting, flag, or option that behaves differently across versions, environments, or operating systems.
- **Multi-attempt error resolution** — an error that required more than one failed fix, where the solution was not obvious from the error message or documentation.
- **Version incompatibilities** — two libraries, tools, or runtimes that conflict at specific version combinations.
- **Novel patterns** — a non-obvious approach that solved a class of problem elegantly.

Do **not** include:

- Standard usage of a well-documented API.
- Project-specific business logic or implementation details that cannot be generalised.
- Insights already surfaced and confirmed during the session (i.e. knowledge units you retrieved via `craic_query` and subsequently called `craic_confirm` on to record that they proved correct).

For each candidate, assign:

- **summary** — one concise sentence describing what was discovered.
- **detail** — two to four sentences explaining the context and why this behaviour exists or matters.
- **action** — a concrete instruction on what to do (start with an imperative verb).
- **domain** — two to five lowercase domain tags (e.g. `["api", "stripe", "rate-limiting"]`).
- **estimated_relevance** — a float between 0.0 and 1.0:
  - 0.8–1.0: broadly applicable across many languages, frameworks, or teams.
  - 0.5–0.8: applicable to a specific ecosystem or toolchain.
  - 0.2–0.5: applicable only under narrow conditions.
- Optionally: **language**, **framework**, **pattern** if relevant.

If the session contained no events meeting the above criteria, skip Steps 4–6 and follow the "no candidates" instruction in Step 7.

### Step 4 — Present candidates to the user

Open with:

```
I identified {N} potential learning candidates from this session worth sharing with the commons.
```

Present each candidate as a numbered entry:

```
{N}. {summary}
   Domain: {domain tags}
   Relevance: {estimated_relevance}
   ---
   {detail}
   Action: {action}
```

After listing all candidates, ask:

```
Reply with a number to approve, "skip {N}" to discard, or "edit {N}" to revise.
You can also reply "all" to approve everything, or "none" to discard everything.
```

### Step 5 — Handle edits

If the user requests an edit, show the current field values and ask which field to change. Apply the changes and confirm the updated candidate before proposing.

### Step 6 — Propose approved candidates

For each approved candidate, call `craic_propose`:

```
craic_propose(
  summary=<summary>,
  detail=<detail>,
  action=<action>,
  domain=<domain list>,
  language=<language or omit>,
  framework=<framework or omit>,
  pattern=<pattern or omit>
)
```

Confirm each inline after the call:

```
Stored: {id} — "{summary}"
```

### Step 7 — Final summary

```
## Session Reflect Complete

{approved} of {total} candidates proposed to CRAIC.
{skipped} skipped.

IDs stored this session:
- {id}: "{summary}"
- ...
```

If no candidates were identified, display:

```
No shareable learnings identified in this session. Sessions with debugging, workarounds, or undocumented behaviour are more likely to produce candidates.
```

## Edge Cases

- **Empty session** — If the session contained only routine tasks, say so and stop after Step 3.
- **All candidates skipped** — Display the summary with 0 proposed.
- **`craic_propose` error** — Report the error inline for that candidate and continue with the next one. Do not abort.
- **`craic_reflect` returns candidates** — Present them alongside any additional candidates you identified. Deduplicate by summary similarity before presenting.
