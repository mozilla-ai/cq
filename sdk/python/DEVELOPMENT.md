# Development

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

## Initial Setup

```bash
git clone https://github.com/mozilla-ai/cq.git
cd cq/sdk/python
make setup
```

## Common Tasks

```bash
make test           # Run all tests.
make lint           # Run pre-commit hooks (format, lint, detect-secrets).
make format         # Auto-format Python files.
make format-check   # Check formatting without modifying files.
make help           # Show all available targets.
```
