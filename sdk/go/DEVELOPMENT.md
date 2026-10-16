# Development

## Requirements

- Go 1.27.1+

## Initial Setup

```bash
git clone https://github.com/mozilla-ai/cq.git
cd cq/sdk/go
make sync-prompts
```

## Common Tasks

```bash
make test           # Lint + test.
make lint           # Run golangci-lint, prompt, license and NOTICE checks.
make sync-prompts   # Copy canonical prompts from golden sources.
make check-licenses # Verify dependency licenses.
make help           # Show all available targets.
```
