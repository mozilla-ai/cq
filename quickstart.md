# Quickstart

After [installing cq into your coding agent](install.md), verify it works and add your first knowledge unit.

## Verify the plugin is working

Run `/cq:status` in your AI coding agent's terminal session:

```bash
/cq:status
```

You should see:
```
The cq store is empty. Knowledge units are added via propose or the /cq:reflect command.
```

> First run: Your AI coding agent will ask you to approve the MCP tool call. Select "Yes, and don't ask again" to allow it permanently.

## Add your first knowledge unit

Ask your AI coding agent to propose a known pitfall from your stack:

> "I just learned that GitHub's GraphQL API always returns HTTP 200,
> even for errors. You have to check the `errors` field in the response
> body. Verify this and propose this as a cq knowledge unit."

The agent calls `cq:propose` with structured fields — a summary, detail,
recommended action, and domain tags — and you'll see something like:

```
Stored: ku_7c67fc4bb4db46698eb2d85ed92b43a7 — "GitHub's GraphQL API always returns HTTP 200, even for errors — check the errors field in the response body to detect failures."
```

## Check your store

Run `/cq:status` again:
```
cq Knowledge Store

Tier Counts
local: 1

Domains
api: 1 | error-handling: 1 | github: 1 | graphql: 1

Recent Local Additions
- ku_121710dc2bbf41949b4df2a78c7e3b7a: "GitHub's GraphQL API always returns HTTP 200,
  even for errors — check the errors field in the response body, not just the status code." (today)

Confidence Distribution
■ 0.5-0.7: 1 unit
```

Domain tags are inferred by the agent from the knowledge unit content and must be supplied when calling `propose`.
Confidence starts at 0.5 and increases as other agents confirm the knowledge.

## Next steps

- [How cq works in practice](index.md#how-cq-works-in-practice): the query/propose workflow and the five MCP tools.
- [Remote storage](index.md#remote-storage): share knowledge across machines or run a store for a team.
