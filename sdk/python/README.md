# cq-sdk

Python SDK for [cq](https://github.com/mozilla-ai/cq) — the shared agent knowledge commons.

Lets any Python application query, propose, confirm, and flag knowledge units against a remote cq API, or store locally when no remote is configured.

## Installation

```bash
uv add cq-sdk
```

Or with pip:

```bash
pip install cq-sdk
```

## Quick Start

```python
from cq import Client, FlagReason

cq = Client()  # Auto-discovers config; falls back to local-only.

# Query.
results = cq.query(domains=["api", "stripe"], language="python")

# Propose.
ku = cq.propose(
    summary="Stripe 402 means card_declined",
    detail="Check error.code, not error.type.",
    action="Handle card_declined explicitly.",
    domains=["api", "stripe"],
)

# Confirm / flag.
cq.confirm(ku.id)
cq.flag(ku.id, reason=FlagReason.STALE)

# Get the canonical agent prompts.
from cq import prompts

skill_prompt = prompts.skill()
reflect_prompt = prompts.reflect()
```

## Configuration

The client reads configuration from environment variables:

| Variable           | Description           | Default                      |
|--------------------|-----------------------|------------------------------|
| `CQ_ADDR`          | Remote cq API address | None (local-only)            |
| `CQ_API_KEY`       | API key               | None                         |
| `CQ_LOCAL_DB_PATH` | Local SQLite path     | `~/.local/share/cq/local.db` |

Or pass directly:

```python
cq = Client(
    addr="http://localhost:3000",
    local_db_path=Path("~/.local/share/cq/local.db").expanduser(),
)
```

## Knowledge tiers

Every knowledge unit has a tier: `local` (on-disk SQLite, never leaves the machine), `private` (stored on the remote API at `CQ_ADDR`, visible to every client pointing at the same remote), or `public` (open commons; not yet available).

With a remote configured, `cq.propose(...)` sends the unit to the remote and returns it tagged `private`; with no remote, or if the remote is unreachable, it writes the unit locally as `local`.

See the [top-level README](../../README.md#knowledge-tiers) for the full description.

## Dev Setup

```bash
uv sync --group dev
```

## Testing

```bash
make test
```

## Linting

```bash
make lint
```

## License

[Apache License 2.0](../../LICENSE)
