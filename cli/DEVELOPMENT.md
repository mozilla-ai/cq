# Development

## Requirements

- Go 1.26.1+
- [golangci-lint](https://golangci-lint.run/welcome/install/)

## Initial Setup

```bash
git clone https://github.com/mozilla-ai/cq.git
cd cq/cli
go mod download
```

The CLI depends on the Go SDK via a `replace` directive in `go.mod`,
so the SDK must be present at `../sdk/go/`. The skill prompt must also
be synced before building:

```bash
cd ../sdk/go && make sync-skill
```

## Common Tasks

```bash
make test      # Lint + test.
make build     # Build the cq binary.
make lint      # Run golangci-lint.
make install   # Copy binary to /usr/local/bin.
make clean     # Remove build artifacts.
make help      # Show all available targets.
```
