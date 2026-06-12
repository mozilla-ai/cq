---
name: cq:status
description: Display cq knowledge store statistics — tier counts (local/private/public), domains, recent local additions, and confidence distribution.
---

# /cq:status

Display a summary of the cq knowledge store.

## Instructions

1. Call the `status` MCP tool (no arguments needed).
2. Format the response as a readable summary using the sections below.

## Output Format

Present the results using this structure:

```
## cq Knowledge Store

### Tier Counts
local: {count} | private: {count} | public: {count}

*local* = on this machine only; *private* = shared with everyone who can reach the same `CQ_ADDR`; *public* = the open commons, shared across every node that participates in it (available when your configured remote serves it).

### Recent Local Additions
- {id}: "{summary}" ({relative time})
- ...

### Confidence Distribution
*(covers local plus your private/org units; excludes the public commons)*

■ 0.7-1.0: {count} units
■ 0.5-0.7: {count} units
■ 0.3-0.5: {count} units
■ 0.0-0.3: {count} units

### Domains
{distinct count} total
{domain} ({count}), {domain} ({count}) ... +{remaining} more
```

The `tier_counts` field contains the tier breakdown. Display all tiers present in the response. Omit tiers with a count of 0.

The `recent` field reflects the local store only. When a remote is configured and reachable, units proposed via `Client.Propose` go directly to the remote and do not appear here. If `recent` is empty, render the section as `(no recent local additions)` so users understand the scope.

The `domain_counts` field maps each domain to its unit count. Domains are the least important section, so render them last and keep them compact: a `{distinct count} total` line, then the most-tagged few on the next line as `{domain} ({count})` (highest count first, ties alphabetical), capped at 8. If more than 8 exist, append the truncation marker after a single space, e.g. `{domain} ({count}) ... +{remaining} more`; do not leave a trailing comma before it.

If the `warnings` field is non-empty, surface each entry prominently above the summary so the counts are not mistaken for the full picture. A warning means stats aggregation degraded; for example, an unreachable or misconfigured remote, in which case the counts reflect the local store only:

```
> ⚠️ {warning}
```

## Empty Store

When all tier counts are 0 (or `tier_counts` is absent), display only:

"The cq store is empty. Knowledge units are added via `propose` or the `/cq:reflect` command."
