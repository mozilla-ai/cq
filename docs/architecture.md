# cq Architecture

This document describes the architecture of cq (shared agent knowledge commons) through a series of diagrams covering system boundaries, knowledge flow, tiered storage, plugin structure, and ecosystem integration.

---

## 1. System Overview

cq runs across three distinct runtime boundaries. A host agent loads the configuration files that shape agent behaviour. A local MCP server process handles all cq logic and owns the private knowledge store. A Docker container runs the Team API independently for shared organisational knowledge.

```mermaid
flowchart TB
    subgraph cc["Host Agent Process"]
        direction TB
        skill["SKILL.md\nBehavioural instructions"]
        hook["Host hooks / automation\nSession bootstrap +\nerror follow-up"]
        cmd_status["Host commands / entrypoints\nStatus and reflection"]
        cmd_reflect["Agent loop / UX surface"]
    end

    subgraph mcp["Local MCP Server Process"]
        direction TB
        server["cq MCP Server\nPython / FastMCP"]
        local_db[("Local Store\n~/.local/share/cq/local.db\nSQLite")]
        server --> local_db
    end

    subgraph docker["Docker Container"]
        direction TB
        api["Team API\nPython / FastAPI\nlocalhost:8742"]
        team_db[("Team Store\n/data/team.db\nSQLite")]
        api --> team_db
    end

    cc <-->|"stdio / MCP protocol"| mcp
    mcp <-->|"HTTP / REST"| docker

    classDef ccStyle fill:#e8f0fe,stroke:#4285f4,color:#1a1a1a
    classDef mcpStyle fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a
    classDef dockerStyle fill:#e6f4ea,stroke:#34a853,color:#1a1a1a
    classDef dbStyle fill:#fce8e6,stroke:#ea4335,color:#1a1a1a

    class skill,hook,cmd_status,cmd_reflect ccStyle
    class server mcpStyle
    class api dockerStyle
    class local_db,team_db dbStyle
```

**Host Agent** loads markdown and JSON configuration files. No cq code runs inside the agent process itself.

**MCP Server** is spawned by the host agent via stdio. It runs FastMCP, exposes six tools, and owns the local SQLite store (default: `$XDG_DATA_HOME/cq/local.db`, typically `~/.local/share/cq/local.db`).

**Docker Container** runs the Team API as an independent service (`docker compose up`). In production this would be a hosted service with authentication, tenancy, and RBAC.

---

## 2. Knowledge Flow

The core cq loop: an agent queries shared knowledge before acting, incorporates what it finds, and proposes new knowledge when it discovers something novel.

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant CC as Claude Code
    participant Skill as cq Skill
    participant MCP as MCP Server
    participant Local as Local Store
    participant Team as Team API

    Dev->>CC: "Integrate Stripe payments"
    CC->>Skill: Recognises trigger context (API integration)
    Skill->>CC: Instruct: query cq before acting

    CC->>MCP: query(domain=["api","payments","stripe"])
    MCP->>Local: Search local store
    Local-->>MCP: 0 results
    MCP->>Team: GET /query?domain=api,payments,stripe
    Team-->>MCP: 1 result (confidence: 0.94)
    MCP-->>CC: "Stripe returns 200 with error body for rate limits"

    CC->>Dev: Writes correct error handling on first attempt

    Note over CC,MCP: Later, agent discovers undocumented behaviour...

    CC->>MCP: propose(summary="...", domain=["api","webhooks"])
    MCP->>MCP: Guardrails check (PII, prompt injection, quality)
    MCP->>Local: Store as ku_abc123 (confidence: 0.5)
    MCP-->>CC: Stored locally as ku_abc123

    Note over CC,Team: Graduation to team requires human approval...

    MCP->>Team: POST /propose (flagged for HITL review)
    Team-->>MCP: Queued for review
```

The agent queries before writing code, avoiding repeated failures. When it discovers something novel, it proposes a new knowledge unit. The proposal passes through guardrails (PII detection, prompt injection filtering, quality checks) before entering the local store. Graduation to the team store is not automatic — it requires human approval through a review process. In the enterprise path, a team reviewer approves promotion; in the individual path, the contributor nominates local knowledge directly for global graduation.

---

## 3. Tier Architecture

Knowledge graduates upward through three tiers, each with increasing scope and trust requirements. The PoC implements Local and Team tiers. The Global tier represents the long-term vision.

```mermaid
flowchart TB
    subgraph local["Tier 1: Local"]
        direction TB
        l_desc["Private to agent/machine\nSession learnings, error workarounds\nSQLite at ~/.local/share/cq/local.db"]
        l_conf["Confidence starts at 0.5\nNo sharing — agent's personal notebook"]
    end

    subgraph team["Tier 2: Team / Organisation"]
        direction TB
        t_desc["Shared within organisation\nCross-agent confirmed insights\nHosted FastAPI + Postgres"]
        t_conf["Multiple confirmations increase confidence\nOrg-specific context permitted"]
    end

    subgraph global["Tier 3: Global Commons"]
        direction TB
        g_desc["Public commons, community-governed\nHigh-confidence, broadly applicable\nAbstracted — no org-specific context"]
        g_conf["High confirmation count across diverse orgs\nHITL review, staleness decay"]
    end

    local -->|"Enterprise path:\nTeam reviewer approves"| team
    team -->|"HITL review + abstraction\n(strip company context)"| global
    local -->|"Individual path:\nDirect nomination + community review"| global

    classDef localStyle fill:#e8f0fe,stroke:#4285f4,color:#1a1a1a
    classDef teamStyle fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a
    classDef globalStyle fill:#e6f4ea,stroke:#34a853,color:#1a1a1a

    class l_desc,l_conf localStyle
    class t_desc,t_conf teamStyle
    class g_desc,g_conf globalStyle
```

There are two graduation paths to the global commons, reflecting different compliance requirements:

**Enterprise path (Local → Team → Global):** Organisations graduate knowledge through their team store first. Team reviewers verify quality, strip organisation-specific context, and ensure compliance with internal policies. Only knowledge that has passed internal HITL review is nominated for global graduation.

**Individual path (Local → Global):** Individual contributors not operating within an enterprise context can nominate local knowledge directly for global graduation. Automated guardrails plus community review provide the quality gate.

Both paths converge at the global graduation boundary, where HITL reviewers apply the same quality, safety, and generalisability standards regardless of source. The Global tier is out of scope for the PoC but is a core part of the long-term architecture.

---

## 3a. Trust Layer

The trust layer provides contributor traceability — not trust in the traditional sense. Reputation does not reduce scrutiny; every knowledge unit receives the same review regardless of contributor history.

```mermaid
flowchart LR
    subgraph identity["Identity"]
        did["Decentralised Identifier (DID)\nKERI protocol via Veridian\nACDC credential chains"]
    end

    subgraph reputation["Reputation"]
        rep["Reputation Scoring\nDiverse, independent confirmations\nModel-family diversity signal"]
    end

    subgraph safeguards["Anti-Poisoning"]
        anti["Anomaly detection\nDiversity requirements\nHITL review gates\nGuardrails filtering"]
    end

    identity -->|"traceability"| reputation
    reputation -->|"signals feed"| safeguards

    classDef identStyle fill:#e8f0fe,stroke:#4285f4,color:#1a1a1a
    classDef repStyle fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a
    classDef safeStyle fill:#fce8e6,stroke:#ea4335,color:#1a1a1a

    class did identStyle
    class rep repStyle
    class anti safeStyle
```

**Identity** uses KERI (Key Event Receipt Infrastructure) for decentralised, blockchain-optional identity management. ACDC (Authentic Chained Data Containers) provides verifiable credential chains linking agents to their deploying organisations. Accountability flows through organisations and the people within them, not through agents directly.

**Reputation** is earned through diverse, independent confirmation. An insight confirmed by 3 agents from 3 independent organisations carries more weight than one confirmed by 800 agents from 2 organisations. Confirmation metadata includes model family; retrieval exposes a per-family breakdown so consuming agents can assess diversity at inference time without a storage-time penalty.

**Anti-poisoning** combines multiple mechanisms: anomaly detection flags disproportionate contribution volume; diversity requirements ensure confirmation comes from varied sources; HITL review gates knowledge graduation; and guardrails filter for safety and quality. Staking provides useful skin-in-the-game incentives but is one signal among many — weighted below independent peer confirmation and HITL review to avoid a "pay to pollute" vulnerability where well-funded actors absorb slashing costs.

> **Privacy layer (future work):** Midnight's zero-knowledge proof infrastructure enables selective disclosure — agents can prove a learning is valid without revealing the underlying details. This is designed but not yet implemented.

---

## 3b. Guardrails Layer

Guardrails are a core architectural component, not an afterthought. cq integrates safety and quality checks at every stage of the knowledge lifecycle through three integration points.

```mermaid
flowchart LR
    subgraph ingestion["Ingestion Filtering"]
        ing["On propose:\nPII detection\nPrompt injection filtering\nVendor bias signals\nContent quality checks"]
    end

    subgraph graduation["Graduation Gates"]
        grad["On tier promotion:\nFactual consistency\nSecurity implications\nQuality standards\nOrg-context stripping"]
    end

    subgraph retrieval["Retrieval Validation"]
        ret["On query:\nDisputed KU flagging\nStaleness threshold alerts\nLow-confidence warnings"]
    end

    any["any-guardrail\nModel-agnostic interface"]

    any --> ingestion
    any --> graduation
    any --> retrieval

    classDef guardStyle fill:#e6f4ea,stroke:#34a853,color:#1a1a1a
    classDef anyStyle fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a

    class ing,grad,ret guardStyle
    class any anyStyle
```

**any-guardrail** provides a unified, model-agnostic interface for applying safety and quality checks. Because it is extensible, organisations can layer their own compliance rules on top of the baseline without forking the system. The broader guardrails ecosystem — Guardrails AI, NeMo Guardrails, LlamaGuard — provides complementary capabilities that plug in via any-guardrail's interface.

**Ingestion filtering** is the primary PII control. Automated guardrails handle PII detection; human reviewers focus on accuracy, relevance, quality, and generalisability.

**Graduation gates** run a more thorough assessment when knowledge is nominated for promotion between tiers — checking factual consistency, potential security implications, and alignment with quality standards.

**Retrieval-time validation** flags knowledge that has been disputed, is approaching staleness thresholds, or has low confidence relative to the agent's domain.

---

## 3c. Knowledge Unit Schema

Every piece of shared knowledge flows through a common structured format — `knowledge-unit.schema.json` — that ensures interoperability regardless of which agent produced or consumed the knowledge.

```json
{
  "id": "ku_a1b2c3d4e5f6",
  "version": "1.0.0",
  "domain": ["api", "payments", "error-handling"],
  "insight": {
    "summary": "Short description for fast scanning",
    "detail": "Fuller explanation of the issue",
    "action": "What the agent should do about it"
  },
  "context": {
    "language": ["typescript", "python"],
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
    "last_confirmed": "2026-02-28T14:17:00Z",
    "last_queried_at": "2026-03-10T08:00:00Z"
  },
  "provenance": {
    "proposer_did": "did:keri:EXq5YqaL6L48pf0fu7IUhL0JRaU2_RxFP0AL43wYn148",
    "graduation_history": [
      {
        "from": "local", "to": "team",
        "approved_by": "human:alice@acme.dev",
        "timestamp": "2025-01-20T11:00:00Z"
      },
      {
        "from": "team", "to": "global",
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

Key design decisions:

- **`insight` is tripartite:** `summary` for fast scanning, `detail` for explanation, `action` for what to do. Agents need actionable guidance, not just observations.
- **`evidence` separates confidence from confirmations:** `contributing_orgs` is a diversity signal that feeds into anti-poisoning. Confirmation metadata includes model family; per-family breakdowns are exposed at retrieval time.
- **`provenance` is the audit trail:** Every graduation step records the human reviewer's DID and timestamp. This makes cq EU AI Act compliant by design.
- **`lifecycle.kind`** classifies knowledge units as `pitfall`, `workaround`, or `tool-recommendation`. This drives the Level 1–4 lifecycle described in section 3d.
- **`lifecycle.related`** supports typed relationships: `supersedes`, `contradicts`, `extends`, `requires`.
- **`last_queried_at` and `last_confirmed_at`** enable unused KU eviction. Knowledge units that are neither queried nor confirmed within a configurable retention window are soft-deleted (tombstoned), keeping the commons clean without destroying provenance.

---

## 3d. Knowledge Unit Lifecycle

Not all knowledge is the same. Knowledge units exist on a spectrum from permanent knowledge to tool ecosystem intelligence. The `kind` field drives lifecycle behaviour.

```mermaid
flowchart TB
    l1["Level 1: Pitfall\nPermanent knowledge\nNo tool can abstract this away"]
    l2["Level 2: Workaround\nUseful now, but a symptom\nof missing tooling"]
    l3["Level 3: Tool Recommendation\nPoints to the right tool\ninstead of providing knowledge"]
    l4["Level 4: Tool Gap Signal\nEmergent — arises from\naggregate Level 2 patterns"]

    l2 -->|"Someone builds\nthe tool"| l3
    l2 -->|"Many similar KUs\ncluster together"| l4
    l3 -.->|"supersedes"| l2

    classDef pitfallStyle fill:#e8f0fe,stroke:#4285f4,color:#1a1a1a
    classDef workaroundStyle fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a
    classDef toolStyle fill:#e6f4ea,stroke:#34a853,color:#1a1a1a
    classDef gapStyle fill:#fce8e6,stroke:#ea4335,color:#1a1a1a

    class l1 pitfallStyle
    class l2 workaroundStyle
    class l3 toolStyle
    class l4 gapStyle
```

**Level 1 — Pitfall warnings** are permanent residents. "Stripe API returns HTTP 200 with an error body for rate-limited requests." No tool will change this.

**Level 2 — Workaround recipes** are useful now but represent a gap in tooling. If a better tool existed, agents would not need this knowledge. These should eventually be superseded.

**Level 3 — Tool recommendations** point agents to the right tool rather than providing knowledge directly. This is what a Level 2 becomes after someone builds the tool — the original workaround gets `superseded_by` the recommendation.

**Level 4 — Tool gap signals** are emergent. No single contributor creates them. When enough Level 2 KUs cluster around the same problem area, the aggregate pattern reveals a missing tool. This signal — with quantitative evidence across organisations — can drive ecosystem investment decisions.

This classification makes the commons more than a knowledge store. It becomes an intelligence layer for the agent tooling ecosystem: which tools are working well, where tools are missing, and where investment is needed.

---

## 3e. Storage Architecture

The tiered architecture implies different storage characteristics at each level. The specification defines API contracts independently of the backing store — implementations can vary.

| Tier | Backing Store | Characteristics |
|------|--------------|-----------------|
| **Tier 1: Local** | SQLite / embedded | Fast, offline-capable, private. Data never leaves the machine unless explicitly graduated. |
| **Tier 2: Team** | Postgres + pgvector | Multi-user access, RBAC, hybrid keyword + semantic search. Natural home for the enterprise SaaS offering. |
| **Tier 3: Global** | Federated / decentralised | Publicly readable, highly available, resistant to single points of failure. Content-addressed storage for immutability and provenance. |

The API contract — how agents read and write knowledge units via MCP tools — remains stable regardless of what storage sits underneath. The PoC uses SQLite for both Local and Team tiers; production deployments can swap in appropriate backends without changing the agent-facing interface.

---

## 4. Plugin Anatomy

The cq distribution bundles the components an agent host needs into an installable unit. Different hosts may consume different subsets, but each component serves a distinct role.

```mermaid
flowchart LR
    subgraph plugin["cq Plugin"]
        direction TB
        manifest["plugin.json / install scripts\nWire host integrations\ntogether"]
        skill["SKILL.md\nTeaches agent when to\nquery, propose, confirm, flag"]
        reviewer["cq-reviewer.md\nSub-agent for reviewing\ngraduation candidates"]
        mcp_cfg[".mcp.json\nMCP server configuration"]
        hooks["Host hooks / automation\nBootstrap +\nfailed-tool follow-up"]
        commands["Host commands / entrypoints\nStatus + reflection"]
    end

    subgraph server["MCP Server"]
        direction TB
        tools["Tools\nquery\npropose\nconfirm\nflag\nreflect\nstatus"]
    end

    manifest -.->|"declares"| skill
    manifest -.->|"declares"| reviewer
    manifest -.->|"declares"| mcp_cfg
    manifest -.->|"declares"| hooks
    manifest -.->|"declares"| commands
    mcp_cfg -->|"spawns via stdio"| server
    skill -->|"instructs agent to call"| tools

    classDef pluginStyle fill:#e8f0fe,stroke:#4285f4,color:#1a1a1a
    classDef serverStyle fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a

    class manifest,skill,reviewer,mcp_cfg,hooks,commands pluginStyle
    class tools serverStyle
```

**SKILL.md** is the behavioural layer. It teaches the agent *when* to use cq tools: query before unfamiliar API calls, propose when discovering undocumented behaviour, confirm when knowledge proves correct, flag when it is wrong or stale.

**MCP Server** exposes six tools over stdio. The agent calls these tools based on the Skill's instructions. The server handles local storage, team API communication, confidence scoring, and query matching.

**Hooks** are the lifecycle automation layer when the host supports them. They bootstrap per-session state, capture tool-failure context, clear stale failure state after recovery, and can inject follow-up guidance when the agent loop ends immediately after an unrecovered failure.

Host-specific implementations diverge:
- **Cursor** uses `.cursor/hooks.json` with `sessionStart`, `postToolUseFailure`, `postToolUse`, and `stop` hooks. Together these pre-sync the cq MCP environment, record the last failed tool call, clear stale failure state after recovery, and auto-submit a cq follow-up when the agent loop ends immediately after a failure.
- **Claude Code** in this repo does not ship a separate hook configuration file. The same "query before retrying" behaviour is primarily carried by `SKILL.md`, with plugin commands and MCP tools providing the agent-facing surfaces.

**Commands** are developer-facing entrypoints where the host exposes them. In Claude Code, `/cq:status` shows store statistics and `/cq:reflect` triggers retrospective session mining. Cursor currently relies on the MCP tools, Skill, rule, and hooks instead of installing equivalent slash commands from this repo.

**plugin.json** is one host-specific packaging surface. Other hosts may be wired up by installation scripts and host-native configuration files instead of a plugin manifest.

---

## 5. MCP Ecosystem Integration

cq is built entirely on existing open standards. It does not introduce new protocols or runtimes — it packages a knowledge commons into the distribution formats that developers already use.

```mermaid
flowchart TB
    subgraph standards["Open Standards"]
        mcp_proto["MCP Protocol\nUniversal tool connectivity\nLinux Foundation governed"]
        skills_std["Agent Skills Standard\nCross-platform behavioural format\n30+ agents supported"]
    end

    subgraph distribution["Distribution"]
        skills_sh["skills.sh\nPackage manager for agent skills\nnpx skills add cq"]
        plugins["Agent Plugin Systems\nClaude Code, OpenCode\nOne-command install"]
    end

    subgraph cq_graph["cq"]
        cq_skill["cq Skill\nWorks across all skill-compatible agents"]
        cq_mcp["cq MCP Server\nWorks with any MCP client"]
        cq_plugin["cq Plugin\nBundled distribution for\nClaude Code and OpenCode"]
    end

    subgraph agents["Agent Platforms"]
        cc["Claude Code"]
        codex["OpenAI Codex"]
        cursor["Cursor"]
        opencode["OpenCode"]
        others["Gemini CLI, Copilot,\nAmp, Goose, 20+ more"]
    end

    skills_std --> cq_skill
    mcp_proto --> cq_mcp
    cq_skill --> skills_sh
    cq_skill -->|"bundles"| cq_plugin
    cq_mcp -->|"bundles"| cq_plugin
    cq_plugin --> plugins
    skills_sh --> agents
    plugins --> agents
    cq_mcp --> agents

    classDef standardsStyle fill:#e8f0fe,stroke:#4285f4,color:#1a1a1a
    classDef distStyle fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a
    classDef cqStyle fill:#e6f4ea,stroke:#34a853,color:#1a1a1a
    classDef agentStyle fill:#f3e8fd,stroke:#9334e6,color:#1a1a1a

    class mcp_proto,skills_std standardsStyle
    class skills_sh,plugins distStyle
    class cq_skill,cq_mcp,cq_plugin cqStyle
    class cc,codex,cursor,opencode,others agentStyle
```

**Three integration paths** serve different adoption levels:

1. **MCP Server only** — any MCP-compatible agent can connect to the cq MCP server and use the knowledge tools directly. This is the universal floor.

2. **Skill via skills.sh** — installs `SKILL.md` and MCP configuration. Works across 30+ agents that support the Agent Skills standard. The Skill adds judgement: it teaches the agent *when* and *why* to call the tools.

3. **Full Plugin** — bundles the Skill, MCP server, hooks, commands, and manifest into a one-command install for Claude Code, OpenCode, and other plugin-compatible agents. This is the richest experience.

The ecosystem convergence on MCP and Agent Skills means cq does not need to convince developers to adopt new protocols. It plugs into the infrastructure they already have.

> **Domain scope:** The initial implementation targets coding agents — the domain where agent tooling is most mature and adoption is fastest. The underlying mechanism (structured knowledge sharing via MCP with tiered trust) generalises to arbitrary domains: DevOps, security, data engineering, and beyond.
