---
name: cq:status
description: Display cq knowledge store statistics — tier counts (local/private/public), domains, recent additions, and confidence distribution.
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

*local* = on this machine only; *private* = shared with everyone who can reach the same `CQ_ADDR`; *public* = open commons (not yet available).

### Domains
{domain}: {count} | {domain}: {count} | ...

### Recent Additions
- {id}: "{summary}" ({relative time})
- ...

### Confidence Distribution
■ 0.7-1.0: {count} units
■ 0.5-0.7: {count} units
■ 0.3-0.5: {count} units
■ 0.0-0.3: {count} units
```

The `tier_counts` field contains the tier breakdown. Display all tiers present in the response. Omit tiers with a count of 0.

If the response includes `promoted_to_remote`, add this line after the total count:

```
Promoted {promoted_to_remote} knowledge units to the remote store at startup.
```

## Empty Store

When all tier counts are 0 (or `tier_counts` is absent):

- **With `promoted_to_remote`:** Show the header, tier counts line, and promotion line. Omit Domains, Recent Additions, and Confidence sections (there is no data to display).
- **Without `promoted_to_remote`:** Display only: "The cq store is empty. Knowledge units are added via `propose` or the `/cq:reflect` command."
