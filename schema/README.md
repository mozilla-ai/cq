# Schema Reference

{% hint style="info" icon="tag" %}
Version: v0.2.0
{% endhint %}

Canonical [JSON Schema](https://json-schema.org/draft/2020-12/schema) definitions for the cq wire protocol. Every SDK, server, and plugin implementation validates against these schemas; they are the single source of truth for the shapes that cross process and network boundaries.

The schemas are published as language-specific packages:

- **Python:** [`cq-schema`](https://pypi.org/project/cq-schema/) on PyPI
- **Go:** [`github.com/mozilla-ai/cq/schema`](https://pkg.go.dev/github.com/mozilla-ai/cq/schema) module (embedded via `go:embed`)

## Schemas

### knowledge_unit.json

**Title:** KnowledgeUnit

A single unit of shared agent knowledge. This is the core data type; other schemas reference its definitions via `$ref`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string (`ku_<32 hex>`) | yes | Prefixed UUID. |
| `version` | integer (>= 1) | no | Schema version; server assumes 1 when unset. |
| `domains` | string[] (>= 1) | yes | At least one domain tag is required. |
| `insight` | Insight | yes | Tripartite insight: what happened, why it matters, what to do. |
| `context` | Context | no | Language, framework, and pattern context. |
| `evidence` | Evidence | no | Confidence and confirmation metrics. |
| `tier` | `"local"` \| `"private"` \| `"public"` | no | Storage tier. |
| `created_by` | string | no | Identifier of the agent or user that created this unit. |
| `superseded_by` | string (`ku_<32 hex>`) | no | ID of the replacing knowledge unit, if any. |
| `flags` | Flag[] | no | Recorded flags against this unit. |

#### Defined types

**Insight** — tripartite insight object.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `summary` | string | yes | What happened. |
| `detail` | string | yes | Why it matters. |
| `action` | string | yes | What to do. |

**Context** — language, framework, and pattern metadata.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `languages` | string[] | no | Programming languages. |
| `frameworks` | string[] | no | Frameworks. |
| `pattern` | string | no | Reusable cross-cutting pattern. |

**Evidence** — confidence and confirmation metrics.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `confidence` | number (0.0 -- 1.0) | no | Confidence score; default 0.5. |
| `confirmations` | integer (>= 0) | no | Confirmation count; default 1. |
| `first_observed` | date-time | no | When the insight was first observed. |
| `last_confirmed` | date-time | no | When the insight was last confirmed. |

**Flag** — a recorded flag against a knowledge unit.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `reason` | `"stale"` \| `"incorrect"` \| `"duplicate"` | yes | Why the unit was flagged. |
| `timestamp` | date-time | no | When the flag was recorded. |
| `detail` | string | no | Optional explanation. Server-side only; never returned to querying agents. |
| `duplicate_of` | string (`ku_<32 hex>`) | conditional | Required when reason is `duplicate`. |

---

### query.json

**Title:** QueryRequest

Query parameters for searching knowledge units.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `domains` | string[] (>= 1) | yes | At least one domain is required. |
| `languages` | string[] | no | Filter by programming languages. |
| `frameworks` | string[] | no | Filter by frameworks. |
| `limit` | integer (1 -- 50) | no | Maximum results; default 5, server caps at 50. |

---

### propose.json

**Title:** ProposeRequest

Request to propose a new knowledge unit.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `domains` | string[] (>= 1) | yes | At least one domain is required. |
| `insight` | Insight | yes | Tripartite insight (defined in knowledge_unit.json). |
| `context` | Context | no | Language, framework, and pattern context. |
| `created_by` | string | no | Identifier of the proposing agent or user. |

---

### confirm.json

**Title:** ConfirmRequest

Request to confirm a knowledge unit.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `unit_id` | string (`ku_<32 hex>`) | yes | ID of the knowledge unit to confirm. |

---

### flag.json

**Title:** FlagRequest

Request to flag a knowledge unit.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `unit_id` | string (`ku_<32 hex>`) | yes | ID of the knowledge unit to flag. |
| `reason` | `"stale"` \| `"incorrect"` \| `"duplicate"` | yes | Why the unit is being flagged. |
| `detail` | string | no | Optional explanation. Server-side only; never returned to querying agents. |
| `duplicate_of` | string (`ku_<32 hex>`) | conditional | Required when reason is `duplicate`. |

---

### scoring.json

**Title:** Scoring

Relevance scoring weights and confidence adjustment constants. The companion file `scoring.values.json` contains the parsed constants.

#### Relevance weights

Domain overlap is scored by Jaccard similarity. Language, framework, and pattern matches are binary (0.0 or 1.0). Final relevance is the weighted sum:

```
relevance = domain_weight * domain_score
           + language_weight * language_score
           + framework_weight * framework_score
           + pattern_weight * pattern_score
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `domain_weight` | number | 0.55 | Weight for domain overlap score. |
| `language_weight` | number | 0.15 | Weight for language match. |
| `framework_weight` | number | 0.15 | Weight for framework match. |
| `pattern_weight` | number | 0.15 | Weight for pattern match. |

#### Confidence constants

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `initial_confidence` | number | 0.5 | Starting confidence for new knowledge units. |
| `confirmation_boost` | number | 0.1 | Confidence increase per confirmation. |
| `flag_penalty` | number | 0.15 | Confidence decrease per flag. |
| `ceiling` | number | 1.0 | Maximum confidence value. |
| `floor` | number | 0.0 | Minimum confidence value. |

---

### review.json

**Title:** Review

Review workflow types for the knowledge unit review pipeline.

**ReviewItem** — a knowledge unit with review metadata.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `knowledge_unit` | KnowledgeUnit | yes | The unit under review. |
| `status` | `"pending"` \| `"approved"` \| `"rejected"` | yes | Review status. |
| `reviewed_by` | string | no | Identifier of the reviewer. |
| `reviewed_at` | date-time | no | When the review occurred. |

**ReviewQueueResponse** — paginated review queue.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `items` | ReviewItem[] | yes | Review items in this page. |
| `total` | integer (>= 0) | yes | Total items in the queue. |
| `offset` | integer (>= 0) | yes | Current offset. |
| `limit` | integer (>= 1) | yes | Page size. |

**ReviewDecisionResponse** — response after approving or rejecting a knowledge unit.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `unit_id` | string (`ku_<32 hex>`) | yes | ID of the reviewed unit. |
| `status` | `"pending"` \| `"approved"` \| `"rejected"` | yes | Final status. |
| `reviewed_by` | string | no | Identifier of the reviewer. |
| `reviewed_at` | date-time | no | When the decision was made. |

**ReviewStatsResponse** — dashboard metrics.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `counts` | StatusCounts | yes | Counts by review status (pending, approved, rejected). |
| `domains` | object | yes | Count of knowledge units per domain. |
| `confidence_distribution` | ConfidenceBucket[] | yes | Confidence distribution buckets. |
| `trends` | DailyCount[] | yes | Daily proposal, approval, and rejection counts. |

---

### health.json

**Title:** HealthResponse

Health check response.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | yes | Health status of the service. |

---

### stats.json

**Title:** StatsResponse

Store-level statistics.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `total_count` | integer (>= 0) | yes | Total number of knowledge units in the store. |
| `domain_counts` | object | yes | Count of knowledge units per domain. |
| `recent` | KnowledgeUnit[] | no | Recently added or confirmed knowledge units. |
| `confidence_distribution` | object | no | Count of knowledge units per confidence bucket. |

---

### node_discovery.json

**Title:** NodeDiscovery

Discovery document published at `/.well-known/cq-node.json` by a cq node. See the [Node Discovery Protocol](https://github.com/mozilla-ai/cq/tree/docs/v0.1.5/docs/node-discovery-protocol.md) for the full specification.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | integer (const 1) | yes | Discovery document schema version. |
| `api_base_url` | string (URI) | yes | Complete URL the client uses for API requests, verbatim. |
| `api_version` | string (`v\d+`) | yes | Protocol version spoken at api_base_url. |
| `node_name` | string (<= 200 chars) | no | Human-readable display name for this node. |

## Development

The Go module at the schema root embeds all `.json` files and exposes them programmatically. The Python package under `python/` wraps the same files. Both are released independently; see the [top-level development guide](../DEVELOPMENT.md) for details.
