.DEFAULT_GOAL := help

PROMPT_SRC_SKILL := ../../plugins/cq/skills/cq/SKILL.md
PROMPT_SRC_REFLECT := ../../plugins/cq/commands/reflect.md
PROMPT_DST_SKILL := src/cq/prompts/SKILL.md
PROMPT_DST_REFLECT := src/cq/prompts/reflect.md

.PHONY: help
help:
	@echo "cq-sdk — Python SDK for the shared agent knowledge commons"
	@echo ""
	@echo "Development:"
	@echo "  make setup              Install all dependencies"
	@echo "  make test               Run all tests"
	@echo "  make lint               Run pre-commit hooks (format, lint, detect-secrets)"
	@echo "  make format             Auto-format Python files"
	@echo "  make format-check       Check formatting without modifying files"
	@echo "  make sync-prompts       Copy canonical prompts into package"
	@echo "  make check-prompts-sync Verify prompt copies match golden sources"

.PHONY: setup
setup:
	uv sync --group dev

.PHONY: sync-prompts
sync-prompts:
	cp $(PROMPT_SRC_SKILL) $(PROMPT_DST_SKILL)
	cp $(PROMPT_SRC_REFLECT) $(PROMPT_DST_REFLECT)

.PHONY: check-prompts-sync
check-prompts-sync:
	@diff -q $(PROMPT_SRC_SKILL) $(PROMPT_DST_SKILL) > /dev/null 2>&1 \
		|| (echo "$(PROMPT_DST_SKILL) is out of sync. Run: make sync-prompts" && exit 1)
	@diff -q $(PROMPT_SRC_REFLECT) $(PROMPT_DST_REFLECT) > /dev/null 2>&1 \
		|| (echo "$(PROMPT_DST_REFLECT) is out of sync. Run: make sync-prompts" && exit 1)
	@echo "✓ Prompts are in sync."

.PHONY: test
test: check-prompts-sync
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
