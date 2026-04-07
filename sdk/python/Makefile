.DEFAULT_GOAL := help

SKILL_SRC := ../../plugins/cq/skills/cq/SKILL.md
SKILL_DST := src/cq/protocol/skill.md

.PHONY: help
help:
	@echo "cq-sdk — Python SDK for the shared agent knowledge commons"
	@echo ""
	@echo "Development:"
	@echo "  make setup          Install all dependencies"
	@echo "  make test           Run all tests"
	@echo "  make lint           Run pre-commit hooks (format, lint, detect-secrets)"
	@echo "  make format         Auto-format Python files"
	@echo "  make format-check   Check formatting without modifying files"
	@echo "  make sync-skill     Copy canonical skill prompt into package"

.PHONY: setup
setup:
	uv sync --group dev

.PHONY: sync-skill
sync-skill:
	cp $(SKILL_SRC) $(SKILL_DST)

.PHONY: test
test: sync-skill
	uv run pytest -x -q

.PHONY: lint
lint:
	uv run pre-commit run --all-files

.PHONY: format
format:
	uv run ruff format .

.PHONY: format-check
format-check:
	uv run ruff format --check .
