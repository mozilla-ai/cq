---
name: cq:reflect
description: Mine the current session for knowledge worth sharing — identify learnings, present them for approval, and propose each approved candidate to the cq knowledge store.
---

# /cq:reflect

Retrospectively mine this session for shareable knowledge units and submit approved candidates to cq.

## Instructions

### Step 1 — Summarize the session context

Construct a compact session summary covering:

- External APIs, libraries, or frameworks used.
- Errors encountered and how each was resolved.
- Workarounds applied for known or unexpected issues.
- Configuration decisions that only work under specific conditions.
- Tool calls that failed before the correct approach was found.
- Any behavior observed that differed from documentation or expectation.
- Dead ends abandoned and why.

The summary should be dense prose — enough for a reader with no prior context to reconstruct the session's technical events. Omit routine file edits, standard library calls, and anything already well-documented.

### Step 2 — Identify candidate knowledge units

Reflection is agent-led — there is no MCP tool for this step. Using your own reasoning, scan the session for insights worth sharing.

A candidate is worth sharing if it meets **all** of these criteria:

1. **Generalizable** — applies beyond this specific project or codebase. Strip all organization-specific names, internal service names, and proprietary identifiers.
2. **Non-obvious** — not directly stated in official documentation, or contradicts documentation.
3. **Actionable** — another agent could apply it immediately with a concrete change.
4. **Novel** — unlikely to already exist in the commons (err toward including, not excluding).

Look specifically for:

- **Undocumented API behavior** — an endpoint returned an unexpected status code, response shape, or side effect.
- **Workarounds for known issues** — a library or tool required a non-standard setup to function correctly.
- **Condition-specific configuration** — a setting, flag, or option that behaves differently across versions, environments, or operating systems.
- **Multi-attempt error resolution** — an error that required more than one failed fix, where the solution was not obvious from the error message or documentation.
- **Version incompatibilities** — two libraries, tools, or runtimes that conflict at specific version combinations.
- **Novel patterns** — a non-obvious approach that solved a class of problem elegantly.

Do **not** include:

- Standard usage of a well-documented API.
- Project-specific business logic or implementation details that cannot be generalized.
- Insights already surfaced and confirmed during the session (i.e. knowledge units you retrieved via `query` and subsequently called `confirm` on to record that they proved correct).

For each candidate, assign:

- **summary** — one concise sentence describing what was discovered.
- **detail** — two to four sentences explaining the context and why this behavior exists or matters.
- **action** — a concrete instruction on what to do (start with an imperative verb).
- **domains** — two to five lowercase domain tags (e.g. `["api", "stripe", "rate-limiting"]`).
- **estimated_relevance** — a float between 0.0 and 1.0:
  - 0.8–1.0: broadly applicable across many languages, frameworks, or teams.
  - 0.5–0.8: applicable to a specific ecosystem or toolchain.
  - 0.2–0.5: applicable only under narrow conditions.
- Optionally: **languages**, **frameworks**, **pattern** if relevant.

If the session contained no events meeting the above criteria, skip Steps 3–5 and follow the "no candidates" instruction in Step 6.

### Step 2.5 — Run the VIBE√ safety check on each candidate

Apply the VIBE√ safety check as defined in the cq skill against every candidate from Step 2. Classify each finding as clean, soft-concern, or hard-finding; for hard findings, generate the sanitized rewrite. Record the classification per candidate — Steps 3 and 6 use these results for presentation and the final summary.

`/cq:reflect` never drops candidates automatically; the user owns the final decision about what to submit.

### Step 3 — Present candidates to the user

Open with:

```
I identified {N_total} potential learning candidates from this session.
{N_hard} have hard concerns and are shown with both the original and a sanitized rewrite — pick which (if either) to store.
{N_soft} have soft concerns flagged with ⚠️ for your awareness.
{N_clean} passed the VIBE√ check cleanly.
```

Present each candidate as a numbered entry. Use one of three templates depending on what Step 2.5 produced.

**Clean candidate:**

```
{N}. {summary}
   Domains: {domain tags}
   Relevance: {estimated_relevance}
   ---
   {detail}
   Action: {action}
```

**Soft-concern candidate** (add the `⚠️` line above the divider):

```
{N}. {summary}
   Domains: {domain tags}
   Relevance: {estimated_relevance}
   ⚠️ {one-line concern}
   ---
   {detail}
   Action: {action}
```

**Hard-finding candidate** (show both versions side by side, with the concern annotated):

```
{N}. {summary}
   Domains: {domain tags}
   Relevance: {estimated_relevance}
   ⚠️ Hard concern: {one-line concern}
   ---
   Original:
     {original detail}
     Action: {original action}
   Sanitized:
     {rewritten detail}
     Action: {rewritten action}
```

If the sanitized rewrite is not coherent (per the Step 2.5 fallback), substitute the Sanitized block with: `Sanitized: (no sanitized version possible — original would not generalize once stripped)`.

After listing all candidates, ask:

```
Reply with a number to approve, "skip {N}" to discard, or "edit {N}" to revise.
For candidates with both an Original and a Sanitized version shown, use "{N} original" or "{N} sanitized" to choose which to store.
You can also reply "all" to approve everything (sanitized version where applicable), or "none" to discard everything.
```

### Step 4 — Handle edits

If the user requests an edit, show the current field values and ask which field to change. Apply the changes and confirm the updated candidate before proposing.

### Step 5 — Propose approved candidates

For each approved candidate, call `propose`:

```
propose(
  summary=<summary>,
  detail=<detail>,
  action=<action>,
  domains=<domain list>,
  languages=<language list or omit>,
  frameworks=<framework list or omit>,
  pattern=<pattern or omit>
)
```

`domains`, `languages`, and `frameworks` are arrays of strings. `pattern` is a single string. Omit optional arguments entirely when not relevant.

Confirm each inline after the call:

```
Stored: {id} — "{summary}"
```

### Step 6 — Final summary

```
## Session Reflect Complete

{approved} of {total} candidates proposed to cq.
{skipped} skipped by user.

VIBE√ findings this session:
- Hard concerns (candidates {numbers}): {one-line concern per candidate}
- Soft concerns (candidates {numbers}): {one-line concern per candidate}

IDs stored this session:
- {id}: "{summary}" [{clean | soft | sanitized | original}]
- ...
```

The bracketed annotation on each stored ID records the VIBE√ provenance of what was stored:

- `clean` — no VIBE√ findings; stored as identified.
- `soft` — soft concern present; stored as-is after the user weighed the flag.
- `sanitized` — hard finding; the user picked the sanitized rewrite.
- `original` — hard finding; the user explicitly picked the unmodified version.

If no candidates were identified, display:

```
No shareable learnings identified in this session. Sessions with debugging, workarounds, or undocumented behavior are more likely to produce candidates.
```

## Edge Cases

- **Empty session** — If the session contained only routine tasks, say so and stop after Step 2.
- **All candidates skipped** — Display the summary with 0 proposed.
- **`propose` error** — Report the error inline for that candidate and continue with the next one. Do not abort.
- **No coherent sanitized rewrite possible** — Present the original with the empty-rewrite note from Step 2.5. The user can still choose to keep the original locally or skip; do not silently drop the candidate.
