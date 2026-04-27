.DEFAULT_GOAL := help

SCHEMA_SRC_DIR := ../
SCHEMA_DST_DIR := src/cq_schema/_data
SCHEMA_FILES := \
	confirm.json \
	flag.json \
	health.json \
	knowledge_unit.json \
	propose.json \
	query.json \
	review.json \
	scoring.json \
	scoring.values.json \
	stats.json

.PHONY: help
help:
	@echo "cq-schema — canonical JSON Schemas and scoring values"
	@echo ""
	@echo "Development:"
	@echo "  make setup              Install all dependencies (runs sync-schema)"
	@echo "  make test               Run all tests"
	@echo "  make lint               Run pre-commit hooks (format, lint)"
	@echo "  make format             Auto-format Python files"
	@echo "  make format-check       Check formatting without modifying files"
	@echo "  make sync-schema        Copy canonical schemas into the package"

.PHONY: setup
setup: sync-schema
	uv sync --group dev

.PHONY: sync-schema
sync-schema:
	@mkdir -p $(SCHEMA_DST_DIR)
	@for f in $(SCHEMA_FILES); do \
		cp $(SCHEMA_SRC_DIR)$$f $(SCHEMA_DST_DIR)/$$f; \
	done

.PHONY: test
test: sync-schema
	uv run pytest -x -q

.PHONY: lint
lint: sync-schema
	uv run pre-commit run --all-files

.PHONY: format
format:
	uv run ruff format .

.PHONY: format-check
format-check:
	uv run ruff format --check .
