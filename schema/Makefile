.DEFAULT_GOAL := help

include ../build/golangci-lint/golangci-lint.mk

.PHONY: help
help:
	@echo "cq canonical schemas (Go module + Python package)"
	@echo ""
	@echo "  make setup              Install Python package dependencies (runs sync-schema)"
	@echo "  make lint               Lint Go module and Python package"
	@echo "  make golangci-lint      Run golangci-lint only"
	@echo "  make test               Test Go module and Python package"
	@echo "  make validate           Validate JSON Schema files and values"
	@echo "  make sync-schema        Copy canonical schemas into the Python package"

.PHONY: setup
setup:
	cd python && $(MAKE) setup

.PHONY: lint
lint: golangci-lint lint-python

.PHONY: lint-python
lint-python:
	cd python && $(MAKE) lint

.PHONY: test
test: test-go test-python

.PHONY: test-go
test-go:
	go test ./... -v

.PHONY: test-python
test-python:
	cd python && $(MAKE) test

.PHONY: validate
validate: validate-fixtures validate-values

.PHONY: validate-fixtures
validate-fixtures:
	uv run --locked --project python check-jsonschema \
		--schemafile knowledge_unit.json \
		fixtures/valid-unit.json \
		fixtures/minimal-unit.json \
		fixtures/flagged-unit.json \
		fixtures/duplicate-flag.json \
		fixtures/extensions-unit.json
	uv run --locked --project python check-jsonschema \
		--schemafile node_discovery.json \
		fixtures/node_discovery_minimal.json \
		fixtures/node_discovery_split.json

.PHONY: validate-values
validate-values:
	uv run --locked --project python check-jsonschema \
		--schemafile scoring.json \
		scoring.values.json

.PHONY: sync-schema
sync-schema:
	cd python && $(MAKE) sync-schema
