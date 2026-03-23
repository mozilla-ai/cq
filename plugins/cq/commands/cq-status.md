---
name: cq:status
description: Display local cq knowledge store statistics — unit count, domains, recent additions, and confidence distribution.
---

# /cq:status

Display a summary of the local cq knowledge store.

## Instructions

1. Call the `status` MCP tool (no arguments needed).
2. Format the response as a readable summary using the sections below.

## Output Format

Present the results using this structure:

```
## cq Local Store

**{total_count} knowledge units**

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

If the response includes `promoted_to_team`, add this line after the total count:

```
Promoted {promoted_to_team} knowledge units to team at startup.
```

## Empty Store

When `total_count` is 0:

- **With `promoted_to_team`:** Show the header, total count line, and promotion line. Omit Domains, Recent Additions, and Confidence sections (there is no data to display).
- **Without `promoted_to_team`:** Display only: "The local cq store is empty. Knowledge units are added via `propose` or the `/cq:reflect` command."
