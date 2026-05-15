# Node Discovery Protocol

## Purpose

A `cq` node serves a frontend (SPA) and a backend (HTTP API). The two pieces can be deployed:

- **Same origin** (single host, single port — the default `./server` Docker image, localhost dev). The reference shape.
- **Split origin** (SPA on a CDN, API on an application load balancer or behind a reverse proxy).

`cq` clients (CLI, Go SDK, Python SDK, MCP server) accept a single `--addr` from the user — typically the human-friendly URL of the node (e.g. `https://example.com`). The discovery protocol lets a node tell those clients where the API actually lives and what protocol version it speaks, without operators having to leak internal hostnames into their UX.

## The Document

A node MAY publish a JSON document at:

```
GET {addr}/.well-known/cq-node.json
```

Content type: `application/json`.

Schema: [`schema/node_discovery.json`](../schema/node_discovery.json).

### Example — split origin

Served from `https://example.com/.well-known/cq-node.json`:

```json
{
  "version": 1,
  "api_base_url": "https://api.example.com/api/v1",
  "api_version": "v1",
  "node_name": "example"
}
```

### Example — same origin (default; document not required)

A node serving the API at `{addr}/api/v1` and the SPA at `{addr}/` MAY omit the document entirely. Clients fall back to:

```
api_base_url = {addr}/api/v1
api_version  = v1
```

### Fields

- `version` (required, integer) — discovery schema version. Currently `1`.
- `api_base_url` (required, string URL) — **complete URL** the client uses verbatim. Client appends only resource paths (e.g. `/knowledge`, `/oauth/start`). Any `/api/v1` prefix lives inside this URL.
- `api_version` (required, string) — protocol version spoken at `api_base_url`. Pattern `v\d+`. Used for compatibility checks, not URL construction.
- `node_name` (optional, string) — human-readable node name for display.

## Client Behavior

Clients MUST:

1. Issue `GET {addr}/.well-known/cq-node.json` once per address per cache TTL.
2. On `404`: use defaults silently (operator did not declare).
3. On `200` with valid JSON conforming to the schema: trust and cache.
4. On `200` with `Content-Type: text/html`: error with a message identifying the likely cause (the addr points at a SPA, not a cq node). Do not fall back.
5. On `200` with malformed JSON: error. Do not fall back.
6. On `5xx` / timeout / connection refused: retry with short backoff (2-3 attempts), then error. Do not fall back.
7. On `api_version` mismatch with the client's supported set: error with the version mismatch surfaced clearly.

Clients MAY:

- Cache the response on disk (CLI) or in memory (SDK, MCP server). Recommended TTL: 24 hours.
- Force refresh via a `--refresh` style flag.

## Operator Recipes

### Reference server (`./server`)

The Docker image at `mozilla-ai/cq-server` is same-origin by construction. No discovery document needed.

### Split-origin behind a CDN or load balancer

Serve a static `cq-node.json` from the SPA origin at the `/.well-known/cq-node.json` path. Set `api_base_url` to the **complete URL clients should call**, including any version prefix the API expects. Whether the API host is internal-only or public is irrelevant — the URL only needs to be reachable from clients.

### Reverse proxy stripping path prefix

If your reverse proxy strips `/api/v1` before reaching the upstream:

```json
{
  "version": 1,
  "api_base_url": "https://api.example.com",
  "api_version": "v1"
}
```

The client calls `https://api.example.com/oauth/start` directly; the proxy is responsible for routing to the right upstream version.

## Protocol Versioning

`version` (the discovery document version) and `api_version` (the cq HTTP API version) evolve independently. A `version: 2` discovery document with breaking changes can still describe a `v1` API and vice versa.
