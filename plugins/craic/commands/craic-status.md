---
name: craic:status
description: Display local CRAIC knowledge store statistics — unit count, domains, recent additions, and confidence distribution.
---

# /craic:status

Display a summary of the local CRAIC knowledge store.

## Instructions

1. Call the `craic_status` MCP tool (no arguments needed).
2. Format the response as a readable summary using the sections below.

## Output Format

Present the results using this structure:

```
## CRAIC Local Store

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

If the store is empty, display: "The local CRAIC store is empty. Knowledge units are added via `craic_propose` or the `/craic:reflect` command."
