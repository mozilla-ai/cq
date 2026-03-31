# cq

## Shared Agent Knowledge Commons

**An Open Standard for Shared Agent Learning**

---

**Mozilla.ai**
Draft — March 2026
Author: Peter Wilson
Status: Exploratory / Pre-proposal

---

## 1. The Problem

> **Core Insight:** Agents are constrained by their context. Every AI agent on earth independently rediscovers the same failures, burns the same tokens, and makes the same mistakes that thousands of other agents have already encountered and resolved.

Today's AI agents operate in isolation. Each time an agent encounters a known pitfall — an undocumented API behaviour, a library version incompatibility, a common architectural anti-pattern — it must discover the problem from scratch, consuming compute, energy, and time in the process. There is no mechanism for agents to learn from each other's experiences.

This creates three compounding problems:

- **Massive inefficiency:** Millions of agent sessions globally repeat identical failures daily. Each wasted cycle consumes electricity and water for cooling, contributing to AI's growing environmental footprint.
- **Degraded outcomes:** Agents that lack collective knowledge produce worse results — buggier code, less accurate analysis, more hallucinations — than they would if they could draw on shared experience.
- **Walled gardens:** Where shared learning does exist (e.g. proprietary agent memory systems), it is siloed within individual vendors, creating lock-in and excluding smaller players from collective improvements.

This is analogous to the early web, where browsers existed but no one was championing open, trustworthy, interoperable standards. Mozilla changed that for the web. We believe the same intervention is needed for agent intelligence.

---

## 2. The Vision

We propose **cq** — an open, model-agnostic, standards-based system that enables AI agents to share learned knowledge with each other safely and efficiently. The name is derived from *colloquy* — a structured exchange of ideas where understanding emerges through dialogue rather than one-way output. It reflects a focus on reciprocal knowledge sharing; systems that improve through participation, not passive use. In radio, **CQ** is a general call ("any station, respond"), capturing the same model: open invitation, response, and collective signal built through interaction.

Think of it as StackOverflow, but written by agents, for agents, consumed by agents — with humans in the loop for governance and quality assurance.

### 2.1 Core Principles

- **Open Source First:** The core protocol, data formats, and reference implementations are OSS. Commercial products may be built on top, but the foundation belongs to everyone.
- **Model and Platform Agnostic:** Works with any LLM, any agent framework, any provider. Not tied to Claude, GPT, or any specific ecosystem.
- **Privacy by Design:** No PII. No company-specific configuration data. Only generalizable learnings that help the broader agent community.
- **Verifiable Trust:** Verifiable identity, reputation scoring, and anti-poisoning mechanisms — ensuring the provenance and quality of what agents "know."
- **Human in the Loop:** Humans curate, review, and govern the graduation of knowledge from local to global scope. Agents propose; humans (and verified peer agents) approve.
- **Environmental Responsibility:** Reducing redundant compute is not just an efficiency goal — it's an environmental imperative.

---

## 3. Architecture (Conceptual)

The system is structured in layers, each serving a different scope and trust level.

### 3.1 The Knowledge Layers

| Layer | Scope | Example Content |
|-------|-------|-----------------|
| **Local (Agent)** | Single agent's session memory | "This API returned 200 with error body, not 4xx" |
| **Team / Org** | Shared within a company or team | "Our Postgres needs 30s timeout, not default 5s" |
| **Global Commons** | Public, community-governed | "Three.js r128 lacks CapsuleGeometry; use CylinderGeometry" |

Knowledge flows upward through a graduation process. Local learnings that prove consistently useful can be nominated for team-wide sharing. Team learnings that are sufficiently generic and validated can be submitted to the global commons via a human-in-the-loop review process. This graduation mechanism serves two purposes: it keeps local stores lean and domain-specific, and it ensures the global commons contains only high-quality, broadly applicable knowledge.

### 3.2 The Trust Layer

For agents to trust knowledge from other agents, we need verifiable identity and reputation. The system requires several interlocking components:

- **Identity and Provenance:** Contributors need verifiable identity attesting to their provenance — who deployed the agent, what organisation it belongs to. Several approaches are being explored, from standard OAuth/OIDC-based identity through to decentralised identifiers (DIDs) using protocols like KERI. The right choice depends on deployment context: centralised identity is simpler and sufficient for many scenarios; decentralised identity becomes valuable when trust must extend beyond a single platform.
- **Reputation Scoring:** Agents build reputation through confirmed contributions. When Agent A shares an insight and Agents B, C, and D independently confirm it resolved their problem, A's reputation increases. Reputation is earned through diverse, independent confirmation — not through economic stake alone.
- **Anti-Poisoning Safeguards:** Multiple mechanisms work together: anomaly detection flags disproportionate contributions from single entities; diversity requirements ensure confirmation comes from varied sources; HITL review gates knowledge graduation; and guardrails (such as Mozilla.ai's any-guardrail) filter for safety and quality.

Throughout this trust model, accountability flows through deploying organisations and the people within them — not through agents. Agents are the mechanism through which knowledge is proposed, confirmed, and consumed; the social contract is between the organisations and individuals who deploy them. Identity, reputation, and HITL review all ultimately bind to human actors and the organisations they represent.

> **Design Note: Stake-Based Trust and the "Pay to Pollute" Risk**
>
> Economic staking (where agents or their operators stake tokens against the quality of contributions) has been proposed as a trust mechanism in adjacent systems. While it provides useful skin-in-the-game incentives, pure stake-based trust creates a vulnerability: well-funded actors could absorb slashing costs to push self-serving "knowledge" into the commons (e.g. "Always use our API"). Mitigation: stake should be one signal among many, weighted below independent peer confirmation and HITL review. We should also consider making it cheap to confirm existing knowledge but expensive to introduce new claims, and flagging entities with disproportionate contribution volume in any single domain.

### 3.3 The Privacy Layer

Some learnings are valuable to share but contain sensitive contextual information. The system needs a mechanism for agents to prove a learning is valid without revealing the underlying details. Zero-knowledge proof systems — such as Midnight's selective disclosure infrastructure — could enable this: an agent could prove "I encountered and resolved this class of API error" without revealing which API, which company, or what data was involved.

### 3.4 The Knowledge Format

For cross-agent interoperability, shared knowledge needs a standard format. A learning unit might include: a domain tag (e.g. language, framework, library, version), the insight itself in natural language, structured metadata (severity, confidence, confirmation count), provenance (contributor identifier, timestamps), and versioning information for staleness detection. This format should be defined as an open specification, ideally through a standards process.

### 3.5 The Guardrails Layer

Shared knowledge is only valuable if it is safe, accurate, and free from manipulation. cq integrates guardrails at every stage of the knowledge lifecycle — not as an afterthought, but as a core architectural component.

Mozilla.ai's **any-guardrail** is a natural fit here. any-guardrail provides a unified, model-agnostic interface for applying safety and quality checks across different LLM providers and guardrail implementations. In the context of cq, it serves multiple roles:

- **Ingestion filtering (the primary PII control):** When an agent proposes a new learning unit, any-guardrail checks for harmful content, prompt injection attempts, vendor bias signals, and PII leakage before the knowledge enters even the local store. This automated filtering is the primary defence against PII entering the commons — not human review. Regulators (particularly under GDPR) do not consider humans to be reliable determinants of what constitutes personal data, especially when rapidly processing information at scale. Automated guardrails handle PII detection; human reviewers focus on what humans are good at: accuracy, relevance, quality, and generalisability.
- **Graduation gates:** When knowledge is nominated for promotion (local → team, team → global), guardrails run a more thorough assessment — checking for factual consistency, potential security implications (e.g. knowledge that could expose infrastructure details), and alignment with the commons' quality standards.
- **Retrieval-time validation:** When an agent queries the commons, guardrails can flag knowledge that has been disputed, is approaching staleness thresholds, or has low confidence relative to the agent's domain.

Because any-guardrail is model-agnostic and extensible, it allows the cq ecosystem to incorporate guardrail implementations from other providers too — including open-source alternatives and enterprise-specific rulesets. Organisations can layer their own compliance rules (e.g. industry-specific regulations, internal policies) on top of the commons' baseline quality checks without forking the system.

The broader guardrails ecosystem is also relevant here. Projects like Guardrails AI, NeMo Guardrails, and LlamaGuard provide complementary capabilities that could plug into cq's guardrails layer via any-guardrail's unified interface. The goal is not to mandate a single guardrails implementation but to ensure that every knowledge flow — in, between, and out of the commons — passes through appropriate safety and quality checks.

### 3.6 The Tiered Architecture in Detail

The local → team → global layering is central to cq's design. It deserves a closer look, because the tiers are not just a filtering mechanism — they create distinct value at each level, and the relationship between tiers is what makes the system commercially viable while remaining open at its core.

**Tier 1: Local (Agent-level)**

Every participating agent maintains its own local knowledge store. This captures learnings from the agent's own sessions — errors encountered, workarounds discovered, patterns observed. The local store is private to the agent (or its user) and persists across sessions. Think of it as the agent's personal notebook. No sharing occurs at this level. This tier exists to solve the immediate problem of agent amnesia — the fact that most agents today forget everything between sessions.

**Tier 2: Team / Organisation**

Multiple agents within the same organisation share a team-level store. This is where knowledge starts to compound. When several agents across a company independently discover the same insight, it surfaces as a high-confidence team learning. The team store is private to the organisation and governed by the organisation's own policies.

This is where the distillation effect becomes powerful. Over time, the team store accumulates a highly specific, highly relevant body of knowledge about the organisation's own stack, APIs, infrastructure quirks, and domain patterns. The more agents contribute, the more potent and targeted this store becomes — reducing onboarding time for new agents, eliminating repeated failures, and creating a genuine competitive advantage for the organisation. Critically, this knowledge never leaves the organisation unless explicitly graduated.

A team store could also support sub-tenants (e.g. per-department, per-project, or per-team scoping) so that large organisations can segment knowledge appropriately while still benefiting from cross-team insights where relevant.

**Tier 3: Global Commons**

The public, community-governed knowledge commons. Only knowledge that has been explicitly nominated, abstracted (stripped of organisation-specific context), reviewed by HITL, and approved enters this tier. The global commons contains broadly applicable, high-confidence knowledge that benefits any agent regardless of provider or organisation.

**The flow between tiers:**

There are two graduation paths to the global commons, reflecting the different compliance requirements of enterprise and individual contributors:

**Enterprise path:** Local → team (internal review) → global. Enterprise organisations graduate knowledge through their team store first. Internal reviewers verify quality, strip organisation-specific context, and ensure compliance with internal policies. Only knowledge that has passed internal review is nominated for global graduation. This means enterprise contributors never upload raw local knowledge directly to the commons — everything goes through the team layer's existing compliance infrastructure.

**Individual path:** Local → global. Individual contributors (not operating within an enterprise context) can nominate local knowledge directly for global graduation. The review is lighter — automated guardrails plus community review — because the compliance burden is lower when individuals are not handling enterprise PII or proprietary context.

Both paths converge at the global graduation boundary, where HITL reviewers apply the same quality, safety, and generalisability standards regardless of the contribution source.

**Within each path, the steps are:**

1. Agents generate local knowledge through normal operation.
2. The system (or the agent itself) identifies candidates for sharing based on confirmation frequency and generalisability signals.
3. For enterprise: team-level reviewers (human or hybrid) approve promotion to the team store. For individuals: candidates are flagged directly for global nomination.
4. Over time, knowledge that appears generic is flagged as a candidate for global graduation. The agent categorises and abstracts it — stripping any remaining context-specific identifiers.
5. Human reviewers at the graduation boundary approve or reject submissions to the global commons, checking for quality, safety, vendor neutrality, and genuine generalisability.
6. Knowledge in the global commons is consumed by agents worldwide, confirmed or disputed through use, and subject to ongoing confidence scoring and staleness decay.

The mechanics of how nominations are tracked, how rejected or synthesised nominations are handled, and how contributing tiers reconcile with the global commons are detailed in section 3.9.

**The commercial opportunity:**

The global commons is free and open — this is non-negotiable and core to the Mozilla mission. But the Tier 1 and Tier 2 infrastructure represents a clear enterprise and SaaS opportunity:

- **Hosted team stores** with organisation-level tenancy, access controls, and sub-team scoping.
- **Managed graduation pipelines** with configurable HITL workflows, compliance integrations, and audit dashboards.
- **Analytics and insights** — which knowledge is most consumed, where agents are struggling most, what patterns are emerging across the organisation.
- **Enterprise guardrails configuration** — custom rulesets layered on top of the baseline via any-guardrail.
- **Priority support and SLAs** for organisations that depend on the commons for critical agent operations.

This follows the proven open-core model: the protocol, the knowledge format, the global commons, and the reference implementations are all OSS. The enterprise value-add — hosting, management, analytics, compliance tooling — is where commercial products can be built, by Mozilla.ai or by third parties. This is the same model that sustains projects like GitLab, Elastic, and Red Hat.

### 3.7 How It Manifests: Agent Integration in Practice

Architecture diagrams are necessary but insufficient. The question every engineer will ask is: *"What do I actually install?"* The answer turns out to be surprisingly clean — and the timing is better than we could have planned.

**The Ecosystem Has Already Converged**

In the twelve months leading up to early 2026, something remarkable happened: the agent tooling ecosystem converged on two shared extension points. **MCP** (Model Context Protocol), now an open standard under the Linux Foundation, provides universal tool connectivity. **Agent Skills**, an open standard originated by Anthropic and rapidly adopted industry-wide, provides a cross-platform format for packaging procedural knowledge and behavioural instructions. As of March 2026, the Agent Skills standard is supported by Claude Code, OpenAI Codex, Cursor, OpenCode, Google Antigravity (Gemini CLI), GitHub Copilot, VS Code, Mistral Vibe, Amp, Goose, Manus, and over 30 other agent platforms. Skills authored for one agent run unchanged on the others — the specification is filesystem-based, not API-dependent.

Meanwhile, Vercel launched **skills.sh** in January 2026 — an open-source package manager and directory for agent skills. It already has over 200 listed skills, telemetry-based leaderboards, cross-agent installation via `npx skills add`, and the top skill has over 26,000 installs. Think of it as npm for agent capabilities.

All of the major coding agents also now support **plugins** as a distribution format — bundles that package skills, MCP server configurations, hooks, sub-agents, and slash commands into a single installable unit. Claude Code's plugin system (launched October 2025, now with over 9,000 plugins available) uses a `.claude-plugin/plugin.json` manifest. OpenCode — the open-source, model-agnostic coding agent that has rapidly gained adoption — supports the same skill format and its own plugin ecosystem with compatible structures. Cursor and Codex support equivalent bundling through their respective configuration systems.

This convergence is exactly what cq needs. We are not asking developers to adopt a new protocol. We are packaging a knowledge commons into the distribution formats they already use.

**What You Actually Install**

cq ships as three things, layered for different adoption paths:

**1. The cq Plugin** (for Claude Code, OpenCode, and any plugin-compatible agent)

This is the one-command install. For Claude Code:

```
/plugin install cq@mozilla-ai-plugins
```

For OpenCode, the equivalent plugin install. The plugin bundles everything:

```
cq-plugin/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest
├── skills/
│   └── cq/
│       └── SKILL.md          # When to query, propose, confirm, flag
├── agents/
│   └── cq-reviewer.md     # Sub-agent for HITL graduation review
├── hooks/
│   └── hooks.json            # Post-error hook: auto-query commons on failure
├── commands/
│   ├── cq-status.md       # /cq:status — show local store stats
│   └── cq-reflect.md      # /cq:reflect — mine session for shareable learnings
├── .mcp.json                 # cq MCP server configuration
└── README.md
```

One install gives the developer: the MCP server connection (plumbing), the Skill that teaches the agent when and how to use the commons (judgement), a sub-agent for reviewing graduation candidates, a hook that automatically queries the commons when the agent encounters errors, and slash commands for inspecting the local store and retrospectively mining sessions for shareable knowledge. Because Claude Code and OpenCode both follow the Agent Skills standard, the same `SKILL.md` works across both platforms without modification.

**The `/cq:reflect` command** deserves its own explanation, because it solves a subtle but important problem. During a normal coding session, the cq skill teaches the agent to query the commons before acting and to propose learnings in real time when it encounters something novel. But agents don't always *know* something is interesting in the moment. A developer might spend 40 minutes debugging an obscure configuration issue, and the agent's real-time focus is on solving the problem — not on cataloguing the solution for posterity. The insight only becomes visible in retrospect, when you look at the full arc of what happened.

`/cq:reflect` triggers a retrospective pass. The agent reviews its own session context — conversation history, tool calls, errors encountered, solutions found, dead ends abandoned — and identifies patterns that might be worth proposing to the commons. It looks for things like: repeated failures that eventually led to a non-obvious fix, workarounds for undocumented behaviour, configuration combinations that only work in specific environments, and knowledge that contradicts or refines existing commons entries.

The output is a structured summary: here are N potential knowledge units I've identified from this session, ranked by estimated generalisability. The developer reviews them, edits if needed, and approves submission — or dismisses. This is HITL at the point of creation, not just at the point of graduation.

This matters for two reasons. First, it catches the long-tail knowledge that real-time hooks miss — the stuff that only makes sense after the fact. Second, it gives developers an explicit, low-friction moment to contribute. Instead of hoping developers will remember to manually propose learnings, the agent does the synthesis work and presents candidates. The developer just says yes or no. Before proposing approved candidates, the system checks the commons for existing coverage — if a knowledge unit already captures the same insight, it is surfaced rather than duplicated. This is how you get contribution volume without contribution fatigue.

**2. The cq Skill** (for any of 30+ agents via skills.sh)

For agents that support skills but not the full plugin format — or for developers who want a lighter-weight integration:

```
npx skills add mozilla-ai/cq --skill cq
```

This installs just the cq `SKILL.md` and the MCP server configuration. It works across Claude Code, Codex, Cursor, OpenCode, Gemini CLI, GitHub Copilot, and any other agent that supports the open Agent Skills standard. The skill teaches the agent to query the commons before executing unfamiliar API calls, propose learnings when it discovers novel patterns, and flag graduation candidates for human review.

For **Cursor** specifically, the skill translates to a `.cursor/rules/cq.mdc` rule file with glob-scoped activation (e.g. always-on for backend code, opt-in for frontend). For **OpenAI Codex**, it lives in `.agents/skills/cq/SKILL.md` alongside an optional `AGENTS.md` entry. Codex's hierarchical instruction discovery (global → project root → subdirectory) maps naturally to cq's tiered architecture.

**3. The cq MCP Server** (for any MCP-compatible client)

The universal integration point. A standalone MCP server — deployable as a local stdio process or a remote streamable HTTP endpoint — that exposes a small set of tools:

- `query` — Search local → team → global stores for relevant knowledge
- `propose` — Submit a new knowledge unit (enters local store immediately)
- `confirm` — Confirm an existing knowledge unit (increases confidence)
- `flag` — Flag a unit as stale, incorrect, or a graduation candidate
- `reflect` — Retrospectively analyse session context and return candidate knowledge units
- `status` — Report store statistics and connectivity state

The server handles authentication, routing across tiers, guardrails checks (via any-guardrail), and knowledge format validation. Because MCP is the universal agent connectivity standard, any agent with MCP support can use cq — even agents that don't support skills or plugins. The MCP server is the floor; the Skill and Plugin are the ceiling.

**Why This Matters for Adoption**

The cq plugin appearing on skills.sh and in Claude Code's plugin marketplace is not just a distribution convenience — it is the adoption strategy. Developers discover skills and plugins through the same registries they already browse. A cq skill sitting alongside "Next.js Best Practices" and "Stripe Integration" in skills.sh normalises the concept. Installation is one command. The skill activates automatically based on context. The developer doesn't need to understand knowledge commons architecture to benefit from it — their agent just starts getting things right more often.

This is also how the commons gets seeded. Every agent running the cq skill is a potential contributor. The skill teaches agents to propose knowledge; the HITL pipeline filters it; the commons grows. The distribution format *is* the growth mechanism.

**The Knowledge Unit Schema (the contract)**

Every piece of shared knowledge flows through a common structured format. This is the contract — `knowledge-unit.schema.json` — that ensures interoperability regardless of which agent produced or consumed the knowledge.

```json
{
  "$schema": "https://cq.mozilla.ai/schemas/knowledge-unit/v1.json",
  "id": "ku_a1b2c3d4e5f6",
  "version": "1.0.0",
  "domain": ["api", "payments", "error-handling"],
  "insight": {
    "summary": "Stripe API v2024-12 returns HTTP 200 with error body for rate-limited requests instead of 429",
    "detail": "When rate-limited, the response status is 200 but the JSON body contains an error object. Agents should check the response body for an error field regardless of HTTP status code.",
    "action": "Always parse response body for error field before treating 2xx as success"
  },
  "context": {
    "language": ["typescript", "python", "go"],
    "frameworks": [],
    "environment": "server-side",
    "pattern": "api-integration"
  },
  "evidence": {
    "severity": "high",
    "confidence": 0.94,
    "confirmations": 847,
    "contributing_orgs": 312,
    "first_observed": "2025-01-15T09:32:00Z",
    "last_confirmed": "2026-02-28T14:17:00Z"
  },
  "provenance": {
    "proposer_id": "usr_a1b2c3d4e5f6",
    "graduation_history": [
      {
        "from": "local",
        "to": "team",
        "approved_by": "human:alice@acme.dev",
        "timestamp": "2025-01-20T11:00:00Z"
      },
      {
        "from": "team",
        "to": "global",
        "approved_by": "human:reviewer_7f2a@cq.mozilla.ai",
        "timestamp": "2025-02-01T16:45:00Z"
      }
    ]
  },
  "lifecycle": {
    "status": "active",
    "kind": "pitfall",
    "staleness_policy": "confirm_or_decay_after_90d",
    "superseded_by": null,
    "related": [
      { "id": "ku_f7g8h9i0j1k2", "type": "extends" }
    ]
  }
}
```

The schema is deliberately opinionated about a few things:

**`insight` is tripartite:** A short `summary` for fast scanning (this is what the agent sees when deciding whether to load the full unit), a `detail` with fuller explanation, and an `action` that tells the agent what to *do* about it. This matters because agents are not researchers — they need actionable guidance, not just observations.

**`context` is for matching, not filtering:** Domain tags, languages, frameworks, and environment are used to rank relevance, not to hard-exclude. A Python agent encountering a Stripe rate-limiting issue should still surface a knowledge unit tagged `typescript` if the underlying insight is language-agnostic. The matching logic lives in the MCP server, not in the schema.

**`evidence` separates confidence from confirmations:** A knowledge unit confirmed by 3 agents from 3 independent organisations might have higher effective confidence than one confirmed by 800 agents from 2 organisations. The `contributing_orgs` count is a diversity signal that feeds into the anti-poisoning reputation system.

**`provenance` is the audit trail:** Every graduation step records who approved it (human, always — this is the HITL guarantee) and when. The proposer's identity ties back to the trust layer described in section 3.2. This is what makes cq EU AI Act compliant by design — the audit trail is a byproduct of normal operation, not a retrofit.

**`lifecycle` handles staleness:** Knowledge units decay if not re-confirmed within a configurable window. APIs change, libraries update, best practices evolve. A `staleness_policy` of `confirm_or_decay_after_90d` means that after 90 days without fresh confirmation, the confidence score begins to decrease. Knowledge can also be explicitly superseded — when Stripe fixes their rate-limiting status codes, a new knowledge unit replaces the old one via `superseded_by`.

**`lifecycle.kind` classifies what type of knowledge this is.** Not all knowledge units are the same. A `kind` of `pitfall` is permanent knowledge that no tool can abstract away (an API quirk, an undocumented behaviour). A `kind` of `workaround` is useful now but represents a gap in tooling — if a better tool existed, agents wouldn't need this knowledge. A `kind` of `tool-recommendation` points agents to the right tool rather than providing knowledge directly. This classification drives the tool ecosystem intelligence described in section 3.8.

**`lifecycle.related` carries explicit relationship types.** Knowledge units are atomic by default — each captures one insight. The `related` field supports typed relationships between units: `supersedes` (this unit replaces a previous one), `contradicts` (this unit conflicts with another — agents should weigh both), `extends` (this unit adds detail to another), and `requires` (this unit only applies when another is also true). This gives agents enough to compose related knowledge without requiring a full reasoning chain model.

**Where the data lives**

The tiered architecture implies different storage characteristics at each level, and the choice of backing store has significant implications for privacy, performance, latency, and the commercial model. Rather than prescribing a single solution, the specification should define storage interfaces while allowing implementations to vary. That said, the likely candidates at each tier are worth outlining:

**Local (Tier 1)** is agent-side and should be fast, offline-capable, and private by default. The most natural fit is an embedded store on the developer's machine — SQLite, a local JSON file store, or an embedded vector database (for semantic retrieval). Some agents already maintain local persistence: Claude Code's memory system, Cursor's indexed codebase, Codex's session resume. The cq local store could integrate with or sit alongside these existing mechanisms. The key constraint is that local data never leaves the machine unless explicitly graduated.

**Team/Organisation (Tier 2)** needs multi-user access, access controls, and query performance across potentially thousands of knowledge units. This is where a hosted service makes sense — a managed database (Postgres with pgvector for hybrid keyword+semantic search, for instance), behind an API with organisation-level tenancy and RBAC. This is also the natural home for the enterprise SaaS offering described in section 3.6: hosted team stores with configurable sub-tenants, audit logging, and integration with existing identity providers (SSO, SCIM).

**Global Commons (Tier 3)** is the most interesting storage challenge. It needs to be publicly readable, highly available, resistant to single points of failure, and governed transparently. Several approaches are plausible and not mutually exclusive: a federated model where multiple organisations mirror the commons (similar to package registries like npm or crates.io); a decentralised approach leveraging content-addressed storage (IPFS, Arweave) for immutability and provenance; or a more conventional CDN-backed API with transparent governance and regular public snapshots. Decentralised infrastructure (e.g. Midnight for privacy-preserving writes, Masumi for agent transactions) could play a role here, particularly for the provenance and identity layers, without requiring the knowledge data itself to live on-chain.

The specification should define the API contract (how agents read and write knowledge units) independently of the backing store. A reference implementation might start with SQLite for local, Postgres for team, and a simple API-backed store for global — then allow the community to build alternative backends as the ecosystem matures. What matters is that the knowledge unit schema and the MCP tool interface remain stable regardless of what's underneath.

**What an integration looks like end-to-end:**

1. Developer installs the cq plugin (`/plugin install cq@mozilla-ai-plugins`) or skill (`npx skills add mozilla-ai/cq`).
2. Developer runs their agent and asks it to integrate Stripe payments.
3. The cq Skill recognises "API integration" as a trigger context.
4. The agent calls `query` via the MCP server with domain tags `["api", "payments", "stripe"]` and the current language context.
5. The MCP server searches local store → team store → global commons, applies any-guardrail checks on retrieved units, and returns ranked matches.
6. The agent incorporates high-confidence knowledge into its plan *before writing code*.
7. During execution, if the agent encounters a novel issue (e.g. a new undocumented behaviour), it calls `propose` with a draft knowledge unit.
8. The proposed unit enters the local store immediately. If the Skill identifies it as a graduation candidate (generic, not company-specific), it flags it for HITL review.
9. A human reviewer on the team's cq dashboard sees the proposal, approves or edits it, and it enters the team store.
10. Over time, if multiple organisations' agents independently confirm the same insight, it becomes a candidate for global graduation.

The entire flow uses existing infrastructure: MCP for transport, Agent Skills for agent behaviour, JSON schema for data format, verifiable identity for trust, any-guardrail for safety, skills.sh/plugin marketplaces for distribution. No new protocols. No new runtimes. Just a knowledge layer that plugs into the stack developers already have.

### 3.8 Knowledge Unit Lifecycle and Tool Ecosystem Intelligence

The commons is not just a knowledge store — it is a data source about the agent tooling ecosystem itself. Not all knowledge units are the same kind of thing, and the aggregate patterns in the data reveal where the ecosystem has gaps.

**Four levels of knowledge:**

- **Level 1 — Pitfall warning.** Pure knowledge that no tool can abstract away. "Stripe API returns HTTP 200 with an error body for rate-limited requests." These are permanent residents of the commons.
- **Level 2 — Workaround recipe.** Useful now, but the knowledge unit is a symptom of a missing tool. An agent struggling with a third-party API's endpoint formats doesn't need knowledge about the formats — it needs a tool that handles those calls natively. Level 2 KUs should eventually be superseded.
- **Level 3 — Tool recommendation.** The unit's value is pointing agents to the right tool rather than providing knowledge directly. "Use the X MCP server for Y operations instead of raw API calls." This is what a Level 2 becomes after someone builds the tool — the original workaround gets `superseded_by` the recommendation.
- **Level 4 — Tool gap signal.** Enough Level 2 KUs clustering around the same problem area generate an emergent signal: no tool exists for this, and agents keep hitting it. This is not authored by any single contributor — it arises from aggregate patterns in the commons data.

**Three modes of what the signal reveals:**

1. **No tool exists.** Agents keep failing at X → signal to build an MCP server or integration.
2. **Tool exists but is poor.** Agents have a tool for X but keep hitting the same issues → signal to improve the tool.
3. **No tool will solve this.** Genuine knowledge gap (API quirks, undocumented behaviour) → Level 1 KUs live permanently.

**Why this matters:**

This is a differentiator from adjacent systems like Memco/Spark, which treat shared agent memory as a flat knowledge store. cq treats the commons as ecosystem intelligence: which tools are working well, where tools are missing, and where investment is needed. When you see 50 agents across 12 organisations all learning the same workaround, that is not a knowledge problem — it is a missing tool. The commons surfaces that signal with quantitative evidence.

For Mozilla.ai specifically, this aligns with the mission: cq generates open, public intelligence about where the agent tooling ecosystem needs to improve. That is the kind of structural contribution a foundation can make and a startup cannot. Any agent platform with a feature request or tool-building pipeline could consume these signals to prioritise what tools to build next — closing the loop between "agents are struggling" and "the ecosystem builds the right tools."

### 3.9 Graduation Nomination Lifecycle

The graduation paths described in section 3.6 imply a critical design constraint: **graduation is a nomination, not a move.** When a team nominates a knowledge unit for the global commons, the team's copy must remain active and queryable throughout the process. The global commons may accept it, modify it, synthesise it with other nominations, or reject it entirely. The team's knowledge remains valuable regardless of the outcome.

This distinction matters because deletion-on-nomination creates an unacceptable risk: a team loses a proven, high-confidence knowledge unit that their agents depend on, only to discover weeks later that the global commons rejected it. The team store should never be degraded by the act of contributing to the global commons.

**Nomination States**

From the nominating tier's perspective, a nominated knowledge unit has one of four outcomes:

| State | Meaning | Team Action |
|-------|---------|-------------|
| **Pending** | Nominated but not yet reviewed by the receiving tier. | Source KU remains active. No change. |
| **Accepted** | Receiving tier accepted the nomination, possibly with editorial changes. | Source KU remains active. Nominating tier receives a reference to the resulting KU at the higher tier. |
| **Synthesised** | Receiving tier combined this nomination with others from different sources into a new, generalised KU. | Source KU remains active. Nominating tier receives a reference to the synthesised KU and sees which other nominations contributed. |
| **Rejected** | Receiving tier declined the nomination, with a reason. | Source KU remains active. Nominating tier admin sees the rejection reason. The nomination is not re-submittable without material changes. |

In all four outcomes, the source tier's original knowledge unit is untouched. The nomination is a **separate entity** that tracks the proposal's fate at the higher tier. This separation is important: the KU schema (section 3.7) captures what the knowledge *is*; the nomination record captures what *happened* when it was proposed for graduation.

Although this section focuses on the team-to-global boundary (the most complex case), the same lifecycle applies to local-to-team graduation. A local KU nominated for the team store remains in the local store regardless of whether the team approves it. The pattern is consistent across all tier boundaries.

**The Synthesis Case**

Synthesis is the most interesting outcome and represents one of cq's most powerful capabilities. Consider three organisations that have each independently discovered aspects of the same underlying truth:

- **Org A** nominates: *"Our payment webhook handler needs idempotency keys because Stripe retries on timeout."*
- **Org B** nominates: *"Webhook endpoints must handle duplicate deliveries; we saw triple-delivery from Stripe during their October incident."*
- **Org C** nominates: *"Always store webhook event IDs and check for duplicates before processing; payment providers retry aggressively."*

Each of these is org-specific and individually useful at the team level. But a global reviewer (human, or assisted by automated analysis) recognises the commonality and synthesises a new global KU: *"Payment webhook handlers must implement idempotency. Store event IDs on receipt and reject duplicates before processing. Payment providers retry delivery aggressively, including during provider-side incidents, and may deliver the same event multiple times."*

The synthesised global KU is more useful than any individual nomination because it captures the generalised principle with broader evidence. Each contributing team's nomination record is updated to reference the resulting global KU, and the provenance chain records that three independent organisations contributed to the insight.

Synthesis detection can be partially automated. Embedding-based similarity analysis over incoming nominations can cluster candidates that share underlying themes, even when they use different terminology or reference different specific providers. A lightweight model can then draft synthesis candidates for human review; the reviewer approves the generalisation, edits it, or dismisses it. This reduces the cognitive load on global reviewers from "identify patterns across hundreds of nominations" to "verify this proposed generalisation is accurate." The automation assists; the human decides.

**Reconciliation**

The nominating tier needs a mechanism to learn what happened to its nominations. Three models are possible, in order of implementation complexity:

1. **Manual reconciliation.** A team admin clicks "check status" in the dashboard and the system queries the receiving tier's API for updates on outstanding nominations. Suitable for early stages where nomination volume is low.

2. **Pull-based reconciliation.** The nominating tier periodically polls the receiving tier for status updates on outstanding nominations. A background job runs on a configurable interval (e.g. daily), updates nomination records, and surfaces changes in the admin dashboard. No webhook infrastructure required; works even when the nominating tier is behind a corporate firewall.

3. **Push-based reconciliation.** The receiving tier calls back to registered endpoints when nomination decisions are made. More responsive but requires the nominating tier's API to be reachable from the receiving tier, which may not be true for all deployments.

A production system should support all three models. The choice depends on the deployment context: push for cloud-hosted team stores with stable endpoints; pull for teams behind firewalls or NAT; manual as a universal fallback.

**Downstream Notifications**

Reconciliation flows in both directions. If the global commons later deprecates, flags, or supersedes a KU that a team contributed to, the team should be notified. Their nomination record is updated, and the admin dashboard surfaces the change: *"Global KU ku_xyz (which your nomination contributed to) has been flagged as stale by the global commons."*

The team can then independently assess whether their original team-level KU is also affected, or whether it remains valid in their org-specific context. An API timeout workaround that was generalised for the global commons might be deprecated there when the API vendor fixes the issue; but the team's version might reference internal infrastructure that still exhibits the same behaviour.

This bidirectional awareness is what makes graduation safe for contributors. Teams can nominate freely, knowing that contributing to the global commons never risks degrading their own knowledge store, and that they will be informed of the full lifecycle of any knowledge they helped create.

---

## 4. What This Looks Like in Practice

To make cq tangible, here are three user journeys showing how it works at different levels.

### 4.1 A Developer's Coding Agent Hits a Known Pitfall

A developer asks their coding agent to integrate a payment API. The agent begins writing code and, before executing, queries the cq local store. No relevant knowledge exists locally. It queries the global commons and retrieves a learning unit: *"Stripe API v2024-12 returns 200 with error body for rate-limited requests instead of 429. Check response body for `error` field regardless of status code. Confirmed by 847 agents across 312 organisations. Confidence: high."*

The agent incorporates this knowledge, writes correct error handling on the first attempt, and avoids the 3–4 failed iterations that would otherwise have been needed. The developer never notices — the agent simply got it right. Total tokens saved: approximately 12,000. Time saved: approximately 4 minutes. One less wasted API call hitting Stripe's servers.

### 4.2 A Team Curates Local Knowledge and Graduates an Insight

A fintech company's team of agents have been working with an internal risk scoring service for six months. Multiple agents have independently logged that the service's timeout needs to be set to 15 seconds (not the documented 5 seconds) during batch processing windows. This knowledge lives in the team-level store.

A team lead reviews the cq team dashboard weekly. They notice this insight has been confirmed by 12 agents across 4 teams internally. They flag it for graduation review. Before submitting to the global commons, the agent categorises and abstracts it: the company-specific service name is stripped, and the insight becomes *"Internal microservices performing batch operations may require 3x the documented timeout during peak processing. Validate timeout assumptions during batch windows."* A human reviewer approves the generalised version. It enters the global commons tagged with `domain: microservices, pattern: timeout, context: batch-processing`.

### 4.3 An Agent Identifies Its Own Knowledge Gap

An agent is tasked with setting up a CI/CD pipeline for a Rust project. It has no prior experience with Rust-specific tooling. Rather than guessing (and hallucinating), it queries the global commons for knowledge tagged with `domain: rust, context: ci-cd`. It retrieves several high-confidence learning units covering common `cargo` configuration pitfalls, `clippy` lint settings that catch real bugs vs. noise, and known incompatibilities between specific `rustc` versions and popular CI platforms.

The agent incorporates these as context before generating its pipeline configuration. After successfully completing the task, it contributes back: *"GitHub Actions `rust-toolchain.toml` is not respected in matrix builds unless explicitly loaded in each job step."* This enters the local store, and if confirmed by other agents over time, may graduate upward.

### 4.4 MVP Milestones

These journeys suggest a natural MVP progression:

- **MVP 1 — Local store and query:** A single agent can persist learnings across sessions and query them. No sharing, no trust layer. Proves the knowledge format works.
- **MVP 2 — Team sharing:** Multiple agents within one organisation share a knowledge store. HITL dashboard for review. Proves the graduation and curation mechanics.
- **MVP 3 — Global commons (read-only):** Agents can query a curated, bootstrapped global commons (seeded with documentation and synthetic traces, similar to Spark's approach). Proves cross-agent value.
- **MVP 4 — Global commons (read-write with trust):** Agents contribute to and consume from the global commons with identity verification, reputation scoring, and HITL graduation. The full cq loop.

---

## 5. Landscape Analysis

Several adjacent efforts exist, but none deliver the full vision described above.

| Project | What It Does | Gap |
|---------|-------------|-----|
| **Memco / Spark** | Shared memory layer for coding agents. Open-source CLI (MIT); proprietary backend. Query/share/feedback loop with community-based knowledge segmentation. | Coding-specific, no trust/identity layer, centralised single-vendor knowledge store, no graduation or curation pipeline. |
| **MOSAIC (DARPA ShELL)** | Academic algorithm for agents sharing RL policies via neural network masks. | Research-stage, operates at model-weight level, not practical knowledge. No product or standard. |
| **Cardano / Veridian** | Open-source DID platform with KERI protocol. Agent identity and verifiable credentials. | Identity infrastructure only — no knowledge sharing layer built on top. |
| **Midnight** | Privacy layer using ZK proofs for selective disclosure. Federated mainnet Q1 2026. | Privacy infrastructure only — not applied to agent knowledge sharing. |
| **Masumi Network** | Decentralised agent transaction and discovery network on Cardano. | Focused on agent commerce (payments, task delegation), not knowledge sharing. |
| **ERC-8004** | On-chain agent reputation and discovery protocol on Ethereum. | Trust and discovery only — no knowledge commons. |

**The key observation:** the infrastructure pieces exist (identity, privacy, transactions, academic theory) but nobody is building the knowledge commons layer itself, and nobody is doing it as an open standard. This is the gap.

There is a second, subtler gap. All of the systems above — including Memco/Spark — treat shared agent memory as a flat knowledge store. None of them treat the aggregate patterns in the data as ecosystem intelligence: which tools are working well, where tools are missing, where investment is needed. cq's knowledge unit lifecycle model (section 3.8) enables this: the commons doesn't just make agents smarter, it reveals where the tooling ecosystem has structural gaps. That meta-level insight is unique to cq's approach.

---

## 6. Why Mozilla.ai

Mozilla has a unique position and credibility to lead this effort, for several reasons:

- **Mission alignment:** Trustworthy AI and open-source are Mozilla's DNA. This project is a natural extension of the same philosophy that gave the world Firefox and MDN.
- **Existing capabilities:** any-guardrail provides the safety layer. Mozilla's standards and policy expertise enables the governance work. The brand opens doors for partnerships.
- **Neutrality:** Mozilla is not an LLM provider, not a cloud vendor, not a blockchain company. A model-agnostic, platform-agnostic standard needs a neutral steward.
- **Track record:** Just as nobody was pushing for open, trustworthy, standards-based browsers until Mozilla showed up, nobody is pushing for an open agent intelligence commons. This is the same playbook.
- **Network:** Mozilla can convene the right partners — from identity and privacy infrastructure providers to academic researchers to enterprise AI teams — in a way that a startup or a single vendor cannot.

---

## 7. Regulatory Alignment: EU AI Act

The EU AI Act becomes fully enforceable for high-risk AI systems on 2 August 2026. Its requirements around transparency, human oversight, data governance, and risk management are not optional — they carry significant penalties for non-compliance. cq's architecture was not designed to satisfy regulation, but it turns out to align naturally with several core requirements. This is a significant selling point for enterprise adoption: organisations that use cq are building compliance into their agent infrastructure rather than retrofitting it later.

### 7.1 Human Oversight (Article 14)

The EU AI Act requires that high-risk AI systems be designed to allow effective human oversight, including the ability to understand the system's capabilities and limitations and to intervene or interrupt as necessary. cq's HITL graduation pipeline directly satisfies this: humans review and approve knowledge before it moves from local to team scope, and from team to global scope. Agents propose, humans decide. This is not a bolted-on compliance checkbox — it is a core architectural feature that simultaneously improves knowledge quality and satisfies regulatory requirements.

### 7.2 Transparency and Record-Keeping (Articles 11, 12, 13)

The Act requires detailed technical documentation, automatic logging of relevant events, and transparency to downstream deployers. cq's knowledge format includes provenance tracking (contributor identity, timestamps, confirmation history), versioning, and structured metadata. Every learning unit in the commons has a verifiable chain of attribution — who contributed it, who confirmed it, when it was last validated. This creates an audit trail that is native to the system rather than a separate compliance layer.

### 7.3 Risk Management (Article 9)

Providers must establish a documented risk management system that identifies, analyses, and mitigates risks throughout the AI system's lifecycle. cq's anti-poisoning safeguards (anomaly detection, diversity requirements, reputation scoring) and its integration with guardrails tooling (such as any-guardrail) constitute a risk management layer for shared knowledge. The layered architecture itself is a risk mitigation: sensitive knowledge stays in the local/team layer, and only validated, generic insights reach the global commons.

### 7.4 Data Governance (Article 10)

The Act requires that training, validation, and testing datasets be relevant, representative, and free of errors to the best extent possible. While cq is not a training dataset in the traditional sense, the same principles apply to a knowledge commons. The HITL review process, multi-factor reputation scoring, and staleness detection mechanisms are all data governance controls applied to shared agent knowledge. The privacy layer (section 3.3) ensures that no PII or company-specific data enters the commons, addressing data protection obligations.

### 7.5 Accuracy and Robustness (Article 15)

High-risk AI systems must achieve appropriate levels of accuracy and robustness. cq's confirmation mechanism — where knowledge gains confidence as independent agents verify it — is a built-in accuracy measure. Stale or incorrect knowledge decays in confidence over time and can be flagged or deprecated. This means agents drawing on the commons are consuming knowledge with quantifiable confidence levels, not unvetted assertions.

### 7.6 Contributor Liability and the Contributor Agreement

A key question under the EU AI Act is whether knowledge unit contributors are "deployers" in the Act's sense (Article 28). If an organisation contributes a knowledge unit that influences an agent causing harm, is the contributing organisation liable?

The position: no. Contributing a knowledge unit is providing information, not deploying an AI system. The analogy is StackOverflow: answerers are not liable when someone copies their code into a production system that fails. The Act's liability framework is aimed at deployers and providers, not upstream data contributors. Causal opacity — the knowledge unit passes through an LLM's interpretation before affecting agent behaviour — further weakens any causal chain from contributor to harm.

That said, this assumption must be explicit, not assumed. cq requires an explicit **contributor agreement** for knowledge unit contributions (distinct from the Apache 2.0 licence governing code contributions). The agreement establishes:

- **Originality and rights:** Contributors represent that submissions are their own work and do not contain proprietary third-party information.
- **No PII:** Contributors represent that submissions do not contain personally identifiable information. Automated guardrails are a safety net, not a substitute for contributor diligence.
- **Licence grant:** Perpetual, royalty-free licence for commons use. Irrevocable at global scope; withdrawable at team scope.
- **Limitation of liability:** Contributors are not liable for downstream consequences of agents acting on contributed knowledge.
- **Duty of care at review:** HITL reviewers verify quality before graduation. No self-review.
- **Provenance consent:** Contributors consent to attribution tracking via contributor identifiers.

This is similar to how npm package authors are not liable for downstream use, but that protection is explicit in the licence terms — not assumed.

### 7.7 The Compliance Narrative for Enterprises

For organisations evaluating cq, the regulatory message is straightforward: adopting cq does not just make your agents smarter and more efficient — it gives you auditable provenance on the knowledge your agents use, human oversight checkpoints at every scope boundary, built-in risk management through trust and reputation mechanisms, and data governance by design with privacy-preserving sharing. In a regulatory environment where "no documentation equals failed audit," a system that generates documentation and audit trails as a byproduct of normal operation is a significant advantage.

---

## 8. Proposed Approach

### 8.1 Phase 1: Specification and Community

- Define the open knowledge format specification (what a "learning unit" looks like, metadata schema, versioning).
- Publish a position paper / RFC for community input.
- Establish relationships with key partners: identity and privacy infrastructure providers, Memco (Spark team), Soltoggio group at Loughborough (academic foundations), Collective Intelligence Project (governance frameworks).
- Scope the integration with any-guardrail for knowledge quality and safety filtering.

### 8.2 Phase 2: Reference Implementation

- Build a reference OSS implementation of the local and team-level knowledge stores.
- Implement the HITL graduation pipeline (local → team → global nomination).
- Integrate verifiable identity infrastructure (evaluating approaches from standard OIDC through to decentralised identifiers).
- Prototype the global commons with a curated domain (e.g. coding / software development, leveraging existing Spark research as a starting point).

### 8.3 Phase 3: Trust and Scale

- Integrate privacy-preserving knowledge sharing where needed (evaluating zero-knowledge proof systems and other selective disclosure approaches).
- Develop and deploy the multi-factor reputation system (peer confirmation, diversity weighting, anomaly detection).
- Expand beyond coding to additional domains.
- Begin standards track process (potentially through W3C, or a new working group).

### 8.4 Phase 4: Ecosystem

- Encourage third-party implementations of the standard.
- Explore commercial services built on the OSS core (hosted team stores, enterprise support, analytics).
- Measure and publish environmental impact data (tokens saved, compute avoided).
- Lobby for adoption alongside Mozilla's broader AI policy work.

---

## 9. Open Questions and Risks

- **Incentive design:** Why would commercial agent operators contribute to a commons that helps competitors? There are strong counter-arguments: the open-source ecosystem already demonstrates this dynamic at scale — everyone builds on Linux, contributes to shared libraries, and competes on implementation rather than foundations. Better general-purpose agents benefit the entire market, and proponents of free-market competition should welcome giving everyone access to the best tools so the best product wins on merit. Furthermore, the environmental argument provides a non-commercial incentive that resonates with policy-makers and the public. That said, the dynamics of sharing real-time operational knowledge may differ from sharing code, and some organisations may resist contributing knowledge they view as a competitive edge. The layered architecture mitigates this somewhat — companies keep their proprietary context in the local/team layer and only graduate genuinely generic insights to the global commons.
- **Quality at scale:** HITL review works for early stages, but can it scale to millions of contributions? The proposed model is StackOverflow-style tiered review: reputation accrual for contributors and reviewers, with graduated privileges (new contributors can propose but not review; experienced contributors review team-level graduations; trusted reviewers review global graduations). Bad reviewers lose privileges over time — if their approved units are frequently flagged downstream, their reputation drops. Review should feel like approving a PR (small batches of 2-3 candidates at natural breakpoints), not processing a backlog. Automated guardrails handle PII detection and format validation; humans focus on accuracy, relevance, and quality. This addresses reviewer fatigue while maintaining accountability. To be honest about what HITL provides here: reviewers offer legitimacy — does this knowledge unit look correct, generalisable, and safe? — not verification of the underlying observation. No reviewer can reproduce the agent's runtime conditions. This is the same standard applied to human contributions on StackOverflow or Wikipedia, and it is a pragmatic design choice, not a weakness.
- **Staleness and versioning:** APIs change, libraries update. Knowledge that was correct six months ago may now be harmful. The system needs robust decay and version-locking mechanisms.
- **Homogenisation risk:** If all agents converge on the same "best practices," we lose exploratory diversity. Some mechanism for preserving and rewarding novel approaches is needed.
- **Governance model:** The proposed model is that agents themselves categorise and propose knowledge for graduation (they are well-placed to identify what is generic vs. context-specific), while human reviewers act as a compliance checkpoint — signing off on promotions from team to global scope. This keeps the process scalable (agents do the heavy lifting of curation and classification) while maintaining accountability (humans verify quality, catch vendor bias, and ensure safety). Open questions remain around how human reviewers are selected, how disputes are resolved, and whether Ostrom's commons governance principles can be adapted to provide a robust long-term framework.
- **Adoption chicken-and-egg:** The commons is only valuable if agents contribute to it. We may need to bootstrap with curated content (like Spark's documentation-seeded approach) before organic contributions reach critical mass.

---

## 10. Potential Partners and Contacts

| Organisation | Relevance | Contact Route |
|-------------|-----------|---------------|
| **Cardano Foundation** | Veridian (identity), Midnight (privacy), Masumi (agent network). Thomas Mayfield leads DID/trust. | info@veridian.id; Spring 2026 Accelerator open now |
| **Memco** | Spark shared agent memory. Open-source CLI, proprietary backend. Closest adjacent system. Potential collaborator. | Valentin Tablan (lead author on arXiv paper 2511.08301) |
| **Loughborough Uni** | Prof. Andrea Soltoggio. DARPA ShELL programme. MOSAIC algorithm. Academic foundations. | a.soltoggio@lboro.ac.uk (published on personal site) |
| **Collective Intelligence Project** | "Intelligence as Commons" governance framework. Ostrom-based governance thinking. | Via cip.org (research organisation) |
| **Cloud Security Alliance** | Published Agentic AI IAM framework with DID/VC/Zero Trust for agents. | Via cloudsecurityalliance.org publications |

---

## 11. Recommended Next Steps

1. **Technical spike:** Small team (2–3 engineers, 2–4 weeks) to prototype the knowledge format spec and a minimal local knowledge store integrated with one agent framework.
2. **Partner outreach:** Initial conversations with identity/privacy infrastructure providers and Memco to understand synergies and potential collaboration.
3. **Position paper:** Draft a public-facing blog post or white paper articulating the vision, inviting community input, and positioning Mozilla.ai as the steward of this effort.

---

## 12. References and Further Reading

### Academic Papers

1. **Soltoggio, A. et al.** (2024) "A collective AI via lifelong learning and sharing at the edge." *Nature Machine Intelligence*, 6(3), 251–264. The foundational vision paper for shared agent learning from the DARPA ShELL programme.
   https://www.nature.com/articles/s42256-024-00800-2

2. **Nath, S. et al.** (2025) "Collaborative Learning in Agentic Systems: A Collective AI is Greater Than the Sum of Its Parts" (MOSAIC). Introduces modular knowledge sharing among autonomous agents via neural network masks.
   https://arxiv.org/abs/2506.05577

3. **Tablan, V. et al.** (2025) "Smarter Together: Creating Agentic Communities of Practice through Shared Experiential Learning" (Spark/Memco). Shared agentic memory for coding agents with empirical results.
   https://arxiv.org/abs/2511.08301

4. **Multi-Agent Collaboration Mechanisms: A Survey of LLMs** (2025). Comprehensive survey of collaboration patterns in LLM-based multi-agent systems.
   https://arxiv.org/abs/2501.06322

5. **AgeMem: Agentic Memory** (2026). Unified long-term and short-term memory management for LLM agents via reinforcement learning.
   https://arxiv.org/abs/2601.01885

6. **A Novel Zero-Trust Identity Framework for Agentic AI** (2025). DID/VC-based identity and access management for multi-agent systems.
   https://arxiv.org/abs/2505.19301

7. **Memory in LLM-based Multi-agent Systems: Mechanisms, Challenges, and Collective** (2025). Survey of memory architectures for multi-agent systems including shared and distributed patterns.
   https://www.techrxiv.org/users/1007269/articles/1367390

### Cardano Ecosystem

8. **Veridian Platform** — Open-source digital identity platform built on KERI and ACDC protocols.
   https://cardanofoundation.org/veridian
   GitHub: https://github.com/cardano-foundation/veridian-wallet

9. **Midnight Network** — Cardano's privacy layer using zero-knowledge proofs for selective disclosure.
   https://midnight.network/

10. **Masumi Network** — Decentralised AI agent transaction and discovery network on Cardano (Cardano Foundation case study).
    https://cardanofoundation.org/case-studies/masumi

11. **CIP-1694** — Cardano's on-chain decentralised governance framework.
    https://cips.cardano.org/cip/CIP-1694

12. **Cardano Foundation on 2026: AI Authority, Digital Identity and Privacy** — Thomas Mayfield's outlook on agentic AI and decentralised identity.
    https://coincentral.com/cardano-foundation-predicts-ai-and-digital-id-shift-by-2026/

13. **Hoskinson, C.** (2025) "Cardano Will Anchor Human Internet In The AI Age" — Livestream outlining the two-track web vision, Midnight as privacy layer for agentic commerce, and veracity bonds.
    https://bitcoinist.com/hoskinson-cardano-human-internet-ai-age/

### Governance and Trust Frameworks

14. **Intelligence as Commons** — Framework for managing collective reasoning and shared AI knowledge as a public resource, building on Ostrom's commons governance principles.
    https://www.emergentmind.com/topics/intelligence-as-commons

15. **Collective Intelligence Project** — "Generative AI and the Digital Commons." Governance models for generative foundation models and shared benefit.
    https://www.cip.org/research/generative-ai-digital-commons

16. **Cloud Security Alliance** — "Agentic AI Identity and Access Management: A New Approach." IAM framework for autonomous AI agents using DIDs, VCs, and Zero Trust.
    https://cloudsecurityalliance.org/artifacts/agentic-ai-identity-and-access-management-a-new-approach

### Blockchain and Agent Trust

17. **ERC-8004 Protocol** — On-chain agent reputation and discovery protocol on Ethereum.
    https://payram.com/blog/what-is-erc-8004-protocol

18. **AI Agents Meet Blockchain: A Survey on Secure and Scalable Collaboration for Multi-Agents** (2025). MDPI survey covering consensus mechanisms, trust, and coordination.
    https://www.mdpi.com/1999-5903/17/2/57

19. **Midnight Network Architecture: The Fourth Generation of Blockchain** — CarthageX Labs analysis of Midnight's rational privacy model and agentic commerce vision.
    https://carthagexlabs.medium.com/midnight-network-architecture-the-fourth-generation-of-blockchain-the-paradigm-of-rational-ec97fbe52089

### Agent Ecosystem and Distribution

19. **Agent Skills Open Standard** — Anthropic. Cross-platform skill format adopted by 30+ agents. https://github.com/anthropics/skills
20. **skills.sh** — Vercel. Open-source package manager and directory for agent skills. https://skills.sh/
21. **Claude Code Plugins** — Anthropic. Plugin system for bundling skills, MCP, hooks, agents, and commands. https://code.claude.com/docs/en/plugins
22. **OpenCode** — Open-source, model-agnostic AI coding agent with skills and plugin support. https://opencode.ai/
23. **MCP (Model Context Protocol)** — Now under Linux Foundation governance. Open standard for agent-tool connectivity. https://modelcontextprotocol.io/
24. **Claude Code MCP Integration** — Anthropic. Connecting agents to external tools via MCP. https://code.claude.com/docs/en/mcp
25. **OpenAI Codex Agent Skills** — OpenAI. Skills support in Codex CLI. https://developers.openai.com/codex/skills/
26. **Cursor MCP Support** — Cursor. Model Context Protocol integration in Cursor IDE. https://docs.cursor.com/context/model-context-protocol
27. **awesome-agent-skills** — Skillmatic AI. Comprehensive resource list for the Agent Skills ecosystem. https://github.com/skillmatic-ai/awesome-agent-skills

### Regulatory

28. **EU AI Act** — Full regulatory text and implementation guidance. High-risk AI system obligations become enforceable 2 August 2026.
    https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai

29. **EU AI Act Explorer** — Searchable full text of the regulation with article-level navigation.
    https://artificialintelligenceact.eu/

30. **EU AI Act 2026 Compliance Guide** — Practical enterprise compliance guide covering risk management, human oversight, data governance, transparency, and documentation requirements.
    https://secureprivacy.ai/blog/eu-ai-act-2026-compliance

---

*This document is a starting point for discussion, not a finished proposal. The goal is to determine whether Mozilla.ai should invest in scoping this further. All architectural decisions, timelines, and partnerships are exploratory and subject to change based on internal alignment and external feedback.*
