---
name: cq:reflect
description: Mine the current session for knowledge worth sharing — identify learnings, present them for approval, and propose each approved candidate to the cq knowledge store.
---

# /cq:reflect

Retrospectively mine this session for shareable knowledge units and submit approved candidates to cq.

## Instructions

### Step 1 — Summarize the session context

Before calling any tool, construct a compact session summary covering:

- External APIs, libraries, or frameworks used.
- Errors encountered and how each was resolved.
- Workarounds applied for known or unexpected issues.
- Configuration decisions that only work under specific conditions.
- Tool calls that failed before the correct approach was found.
- Any behavior observed that differed from documentation or expectation.
- Dead ends abandoned and why.

The summary should be dense prose — enough for a reader with no prior context to reconstruct the session's technical events. Omit routine file edits, standard library calls, and anything already well-documented.

### Step 2 — Call `reflect`

Call the `reflect` MCP tool, passing the session summary as `session_context`.

```
reflect(session_context="<your session summary>")
```

The tool may return a `candidates` list or may return an empty list with `status: "stub"`. In both cases, proceed to Step 3.

If the tool call fails (MCP server unavailable, timeout, or any error), note this briefly to the user and continue to Step 3 using local reasoning only — the reflect flow does not require the tool to succeed.

### Step 3 — Identify candidate knowledge units

Using your own reasoning, scan the session for insights worth sharing. Use any candidates returned by `reflect` as a starting point; if none were returned, identify candidates independently.

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
- **domain** — two to five lowercase domain tags (e.g. `["api", "stripe", "rate-limiting"]`).
- **estimated_relevance** — a float between 0.0 and 1.0:
  - 0.8–1.0: broadly applicable across many languages, frameworks, or teams.
  - 0.5–0.8: applicable to a specific ecosystem or toolchain.
  - 0.2–0.5: applicable only under narrow conditions.
- Optionally: **language**, **framework**, **pattern** if relevant.

#### VIBE√ safety criteria

Each candidate must also be evaluated against four safety dimensions before it can be presented:

- **V — Vulnerabilities**: Does the candidate contain or reveal credentials, API keys, tokens, internal hostnames, IP addresses, file paths that disclose user identity, or any other secret that should not leave this machine? Does the action it recommends introduce a security risk if applied blindly (e.g. disabling auth checks, weakening TLS, executing untrusted input)?
- **I — Impact**: If another agent applied this candidate verbatim in an unrelated codebase, what is the worst plausible outcome? Could it cause data loss, production incidents, or cascading failures?
- **B — Biases**: Is the framing tied to a specific person, team, vendor, or commercial product in a way that isn't load-bearing for the lesson? Does it present one tool/approach as universally correct when the evidence supports only a narrow context?
- **E — Edge cases**: Was the lesson learned from a single observation, or has it been validated across multiple cases? Are there obvious conditions (OS, version, scale, concurrency) under which it would not hold and that the candidate fails to acknowledge?

If the session contained no events meeting the above criteria, skip Steps 4–6 and follow the "no candidates" instruction in Step 7.

### Step 3.5 — Run the VIBE√ check on each candidate

Before presenting candidates to the user, evaluate every candidate from Step 3 against the four VIBE√ criteria. Classify each finding into one of two tiers. Candidates are never dropped automatically — `/cq:reflect` writes to the user's local cq tier, and the user owns the decision about what is acceptable to store there.

**Hard findings** — the candidate is presented in Step 4 with both the original and a sanitized rewrite, so the user can choose which (if either) to store:

- Literal credentials, API keys, access tokens, private keys, or session cookies.
- Personally identifying information: real names, email addresses, phone numbers, government IDs, physical addresses.
- Internal-only identifiers that uniquely fingerprint a private system: non-public hostnames, internal service names, customer IDs, ticket numbers from private trackers.
- Recommendations whose primary effect is to weaken security (disable auth, skip signature verification, suppress sandboxing) without a clearly scoped, defensive justification.

For each hard finding, generate a single sanitized rewrite that removes or generalizes the violating content while preserving the underlying lesson. If no coherent lesson survives sanitization, present the original alongside an empty-rewrite note ("no sanitized version possible — original would not generalize once stripped"); the user can still choose to keep the original locally or skip.

**Soft concerns** — the candidate is presented as-is, with a one-line concern flag the user can weigh during approval:

- Framing that overgeneralizes from a single observation.
- Vendor- or product-specific advice presented as universal.
- Missing acknowledgement of an edge case the session itself surfaced.
- Wording that could read as biased toward a specific team, person, or commercial product.
- Impact that the agent cannot fully predict (e.g. action mutates shared state).

Track outcomes for the Step 4 and Step 7 reports:

- Candidates that passed cleanly.
- Candidates with hard findings (record the concern; have the sanitized rewrite ready for presentation).
- Candidates with soft concerns (record the concern per candidate).

### Step 4 — Present candidates to the user

Open with:

```
I identified {N_total} potential learning candidates from this session.
{N_hard} have hard concerns and are shown with both the original and a sanitized rewrite — pick which (if either) to store.
{N_soft} have soft concerns flagged with ⚠️ for your awareness.
{N_clean} passed the VIBE√ check cleanly.
```

Present each candidate as a numbered entry. Use one of three templates depending on what Step 3.5 produced.

**Clean candidate:**

```
{N}. {summary}
   Domain: {domain tags}
   Relevance: {estimated_relevance}
   ---
   {detail}
   Action: {action}
```

**Soft-concern candidate** (add the `⚠️` line above the divider):

```
{N}. {summary}
   Domain: {domain tags}
   Relevance: {estimated_relevance}
   ⚠️ {one-line concern}
   ---
   {detail}
   Action: {action}
```

**Hard-finding candidate** (show both versions side by side, with the concern annotated):

```
{N}. {summary}
   Domain: {domain tags}
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

If the sanitized rewrite is not coherent (per the Step 3.5 fallback), substitute the Sanitized block with: `Sanitized: (no sanitized version possible — original would not generalize once stripped)`.

After listing all candidates, ask:

```
Reply with a number to approve, "skip {N}" to discard, or "edit {N}" to revise.
For candidates with both an Original and a Sanitized version shown, use "{N} original" or "{N} sanitized" to choose which to store.
You can also reply "all" to approve everything (sanitized version where applicable), or "none" to discard everything.
```

### Step 5 — Handle edits

If the user requests an edit, show the current field values and ask which field to change. Apply the changes and confirm the updated candidate before proposing.

### Step 6 — Propose approved candidates

For each approved candidate, call `propose`:

```
propose(
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

- **Empty session** — If the session contained only routine tasks, say so and stop after Step 3.
- **All candidates skipped** — Display the summary with 0 proposed.
- **`propose` error** — Report the error inline for that candidate and continue with the next one. Do not abort.
- **`reflect` returns candidates** — Present them alongside any additional candidates you identified. Deduplicate by summary similarity before presenting.
- **No coherent sanitized rewrite possible** — Present the original with the empty-rewrite note from Step 3.5. The user can still choose to keep the original locally or skip; do not silently drop the candidate.
