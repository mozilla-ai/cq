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

Apply the VIBE√ safety check as defined in the cq skill against every candidate from Step 2. Classify each finding as clean, soft-concern, or hard-finding. For hard findings, generate the sanitized rewrite covering every `propose` field that could carry the violating content (`summary`, `detail`, `action`, `domains`, `languages`, `frameworks`, `pattern`). Record the classification per candidate — Steps 3 and 6 use these results for presentation and the final summary.

If a hard finding cannot be coherently sanitized, the candidate fails Step 2's generalizable criterion — drop it from the candidate list and record the exclusion in Step 6's summary. Do not present it. `/cq:reflect` never silently drops *presented* candidates; the user owns the final decision on every candidate that reaches Step 3.

### Step 3 — Present candidates to the user

Open with:

```
cq identified {total} potential learning candidates from this session...

{hard} have hard concerns and are shown with both the original and a sanitized rewrite — pick which (if either) to store.
{soft} have soft concerns flagged with ⚠️ for your awareness.
{clean} passed the VIBE√ check cleanly.
```

Omit any count line whose value is zero.

Present each candidate as a numbered entry. Use one of three templates depending on what Step 2.5 produced. Every template has a blank line after the `{N}. {summary}` header so the metadata block is visually distinct.

**Clean candidate:**

```
{N}. {summary}

   Domains: {domain tags}
   Relevance: {estimated_relevance}
   ---
   {detail}
   Action: {action}
```

**Soft-concern candidate** (add the `⚠️` line as the first line of the metadata block, above `Domains`):

```
{N}. {summary}

   ⚠️ {one-line concern}
   Domains: {domain tags}
   Relevance: {estimated_relevance}
   ---
   {detail}
   Action: {action}
```

**Hard-finding candidate.** The header `summary` and `Domains` use the sanitized values — the header never shows hard-finding content. The Original block shows the full original fields (summary, domains, detail, action). The Sanitized block shows only fields that differ from the header, i.e. detail and action.

```
{N}. {sanitized summary}

   ⚠️ Hard concern: {one-line concern}
   Domains: {sanitized domain tags}
   Relevance: {estimated_relevance}
   ---
   Original:
     Summary: {original summary}
     Domains: {original domain tags}
     Detail: {original detail}
     Action: {original action}
   Sanitized:
     Detail: {sanitized detail}
     Action: {sanitized action}
```

After listing all candidates, show the command reference:

```
Commands:
  N              approve (sanitized version for hard-findings)
  N original     approve original instead (hard-findings only)
  edit N         revise before storing
  skip N         discard
  all            approve every candidate's default
  none           discard everything

Combine with commas: e.g. "1, 3 original, skip 2" applies each command in order.
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

{total} candidates identified. {excluded} dropped by VIBE√ (not generalizable; not presented).
{approved} proposed to cq. {skipped} skipped by user.

VIBE√ findings this session:
- Hard concerns (candidates {numbers}): {one-line concern per candidate}
- Soft concerns (candidates {numbers}): {one-line concern per candidate}
- Excluded (not presented): {one-line reason per excluded candidate}

IDs stored this session:
- {id}: "{summary}" [{clean | soft | sanitized | original}]
- ...
```

Omit any VIBE√ findings line whose category has no entries, and omit the `excluded` count sentence if zero.

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
