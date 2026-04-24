# Development

## Requirements

- Go 1.26.1+
- [golangci-lint](https://golangci-lint.run/welcome/install/)

## Initial Setup

```bash
git clone https://github.com/mozilla-ai/cq.git
cd cq/sdk/go
make sync-prompts
```

## Common Tasks

```bash
make test           # Lint + test.
make lint           # Run golangci-lint.
make sync-prompts   # Copy canonical prompts from golden sources.
make check-licenses # Verify dependency licenses.
make help           # Show all available targets.
```
