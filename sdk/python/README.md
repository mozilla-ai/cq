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

# Get the canonical agent protocol prompt.
prompt = cq.prompt()
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
    addr="http://localhost:8742",
    local_db_path=Path("~/.local/share/cq/local.db").expanduser(),
)
```

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
