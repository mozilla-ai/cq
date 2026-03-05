# CRAIC Architecture

This document describes the architecture of CRAIC (Collective Reciprocal Agent Intelligence Commons) through a series of diagrams covering system boundaries, knowledge flow, tiered storage, plugin structure, and ecosystem integration.

---

## 1. System Overview

CRAIC runs across three distinct runtime boundaries. Claude Code loads the plugin configuration files that shape agent behaviour. A local MCP server process handles all CRAIC logic and owns the private knowledge store. A Docker container runs the Team API independently for shared organisational knowledge.

```mermaid
flowchart TB
    subgraph cc["Claude Code Process"]
        direction TB
        skill["SKILL.md\nBehavioural instructions"]
        hook["hooks.json\nPost-error auto-query"]
        cmd_status["/craic:status\nStore statistics"]
        cmd_reflect["/craic:reflect\nSession mining"]
    end

    subgraph mcp["Local MCP Server Process"]
        direction TB
        server["CRAIC MCP Server\nPython / FastMCP"]
        local_db[("Local Store\n~/.craic/local.db\nSQLite")]
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

**Claude Code** loads markdown and JSON configuration files. No CRAIC code runs inside the agent process itself.

**MCP Server** is spawned by Claude Code via stdio. It runs FastMCP, exposes five tools, and owns the local SQLite store at `~/.craic/local.db`.

**Docker Container** runs the Team API as an independent service (`docker compose up`). In production this would be a hosted service with authentication, tenancy, and RBAC.

---

## 2. Knowledge Flow

The core CRAIC loop: an agent queries shared knowledge before acting, incorporates what it finds, and proposes new knowledge when it discovers something novel.

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant CC as Claude Code
    participant Skill as CRAIC Skill
    participant MCP as MCP Server
    participant Local as Local Store
    participant Team as Team API

    Dev->>CC: "Integrate Stripe payments"
    CC->>Skill: Recognises trigger context (API integration)
    Skill->>CC: Instruct: query CRAIC before acting

    CC->>MCP: craic_query(domain=["api","payments","stripe"])
    MCP->>Local: Search local store
    Local-->>MCP: 0 results
    MCP->>Team: GET /query?domain=api,payments,stripe
    Team-->>MCP: 1 result (confidence: 0.94)
    MCP-->>CC: "Stripe returns 200 with error body for rate limits"

    CC->>Dev: Writes correct error handling on first attempt

    Note over CC,MCP: Later, agent discovers undocumented behaviour...

    CC->>MCP: craic_propose(summary="...", domain=["api","webhooks"])
    MCP->>Local: Store as ku_abc123 (confidence: 0.5)
    MCP->>Team: POST /propose (insight is generic, no org-specific refs)
    MCP-->>CC: Stored and shared as ku_abc123
```

The agent queries before writing code, avoiding repeated failures. When it discovers something novel, it proposes a new knowledge unit that enters the local store immediately and, if the insight is generic, also pushes to the team store.

---

## 3. Tier Architecture

Knowledge graduates upward through three tiers, each with increasing scope and trust requirements. The PoC implements Local and Team tiers. The Global tier represents the long-term vision.

```mermaid
flowchart TB
    subgraph local["Local Tier"]
        direction TB
        l_desc["Private to agent/machine\nSession learnings, error workarounds\nSQLite at ~/.craic/local.db"]
        l_conf["Confidence starts at 0.5\nNo sharing — agent's personal notebook"]
    end

    subgraph team["Team Tier"]
        direction TB
        t_desc["Shared within organisation\nCross-agent confirmed insights\nDocker-hosted FastAPI + SQLite"]
        t_conf["Multiple confirmations increase confidence\nOrg-specific context permitted"]
    end

    subgraph global["Global Tier"]
        direction TB
        g_desc["Public commons, community-governed\nHigh-confidence, broadly applicable\nAbstracted — no org-specific context"]
        g_conf["847 confirmations across 312 orgs\nHITL review, staleness decay"]
    end

    local -->|"Agent proposes generic insight\n(no org-specific references)"| team
    team -->|"HITL review + abstraction\n(strip company context)"| global

    classDef localStyle fill:#e8f0fe,stroke:#4285f4,color:#1a1a1a
    classDef teamStyle fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a
    classDef globalStyle fill:#e6f4ea,stroke:#34a853,color:#1a1a1a

    class l_desc,l_conf localStyle
    class t_desc,t_conf teamStyle
    class g_desc,g_conf globalStyle
```

**Local to Team:** The MCP server automatically pushes knowledge to the team store when a proposed insight is generic (no organisation-specific references). In production, HITL review gates this transition.

**Team to Global:** Knowledge that has been independently confirmed across multiple teams is flagged as a graduation candidate. Human reviewers abstract it (stripping company-specific identifiers) and approve entry into the global commons. This tier is out of scope for the PoC but is a core part of the long-term architecture.

---

## 4. Plugin Anatomy

The CRAIC plugin bundles everything an agent needs into a single installable unit. Each component serves a distinct role.

```mermaid
flowchart LR
    subgraph plugin["CRAIC Plugin"]
        direction TB
        manifest["plugin.json\nWires everything together"]
        skill["SKILL.md\nTeaches agent when to\nquery, propose, confirm, flag"]
        mcp_cfg[".mcp.json\nMCP server configuration"]
        hooks["hooks.json\nPost-error: auto-query\ncommons on failure"]
        commands["Commands\n/craic:status — store stats\n/craic:reflect — session mining"]
    end

    subgraph server["MCP Server"]
        direction TB
        tools["Tools\ncraic_query\ncraic_propose\ncraic_confirm\ncraic_flag\ncraic_reflect"]
    end

    manifest -.->|"declares"| skill
    manifest -.->|"declares"| mcp_cfg
    manifest -.->|"declares"| hooks
    manifest -.->|"declares"| commands
    mcp_cfg -->|"spawns via stdio"| server
    skill -->|"instructs agent to call"| tools

    classDef pluginStyle fill:#e8f0fe,stroke:#4285f4,color:#1a1a1a
    classDef serverStyle fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a

    class manifest,skill,mcp_cfg,hooks,commands pluginStyle
    class tools serverStyle
```

**SKILL.md** is the behavioural layer. It teaches the agent *when* to use CRAIC tools: query before unfamiliar API calls, propose when discovering undocumented behaviour, confirm when knowledge proves correct, flag when it is wrong or stale.

**MCP Server** exposes five tools over stdio. The agent calls these tools based on the Skill's instructions. The server handles local storage, team API communication, confidence scoring, and query matching.

**Hooks** trigger automatically. The post-error hook instructs the agent to call `craic_query` with the error context before attempting a fix.

**Commands** are developer-facing. `/craic:status` shows store statistics. `/craic:reflect` triggers retrospective session mining and presents candidate knowledge units for human approval.

**plugin.json** is the manifest that declares all components and wires them together for one-command installation.

---

## 5. MCP Ecosystem Integration

CRAIC is built entirely on existing open standards. It does not introduce new protocols or runtimes — it packages a knowledge commons into the distribution formats that developers already use.

```mermaid
flowchart TB
    subgraph standards["Open Standards"]
        mcp_proto["MCP Protocol\nUniversal tool connectivity\nLinux Foundation governed"]
        skills_std["Agent Skills Standard\nCross-platform behavioural format\n30+ agents supported"]
    end

    subgraph distribution["Distribution"]
        skills_sh["skills.sh\nPackage manager for agent skills\nnpx skills add craic"]
        plugins["Agent Plugin Systems\nClaude Code, OpenCode, Cursor\nOne-command install"]
    end

    subgraph craic["CRAIC"]
        craic_skill["CRAIC Skill\nWorks across all skill-compatible agents"]
        craic_mcp["CRAIC MCP Server\nWorks with any MCP client"]
        craic_plugin["CRAIC Plugin\nBundled distribution for\nClaude Code and OpenCode"]
    end

    subgraph agents["Agent Platforms"]
        cc["Claude Code"]
        codex["OpenAI Codex"]
        cursor["Cursor"]
        opencode["OpenCode"]
        others["Gemini CLI, Copilot,\nAmp, Goose, 20+ more"]
    end

    skills_std --> craic_skill
    mcp_proto --> craic_mcp
    craic_skill --> skills_sh
    craic_plugin --> plugins
    skills_sh --> agents
    plugins --> agents
    craic_mcp --> agents

    classDef standardsStyle fill:#e8f0fe,stroke:#4285f4,color:#1a1a1a
    classDef distStyle fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a
    classDef craicStyle fill:#e6f4ea,stroke:#34a853,color:#1a1a1a
    classDef agentStyle fill:#f3e8fd,stroke:#9334e6,color:#1a1a1a

    class mcp_proto,skills_std standardsStyle
    class skills_sh,plugins distStyle
    class craic_skill,craic_mcp,craic_plugin craicStyle
    class cc,codex,cursor,opencode,others agentStyle
```

**Three integration paths** serve different adoption levels:

1. **MCP Server only** — any MCP-compatible agent can connect to the CRAIC MCP server and use the knowledge tools directly. This is the universal floor.

2. **Skill via skills.sh** — installs `SKILL.md` and MCP configuration. Works across 30+ agents that support the Agent Skills standard. The Skill adds judgement: it teaches the agent *when* and *why* to call the tools.

3. **Full Plugin** — bundles the Skill, MCP server, hooks, commands, and manifest into a one-command install for Claude Code, OpenCode, and other plugin-compatible agents. This is the richest experience.

The ecosystem convergence on MCP and Agent Skills means CRAIC does not need to convince developers to adopt new protocols. It plugs into the infrastructure they already have.
