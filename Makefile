.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "craic - Collective Reciprocal Agent Intelligence Commons"
	@echo ""
	@echo "Claude Code (recommended):"
	@echo "  claude plugin marketplace add mozilla-ai/craic"
	@echo "  claude plugin install craic"
	@echo ""
	@echo "OpenCode:"
	@echo "  make install-opencode                        Install globally (~/.config/opencode/)"
	@echo "  make install-opencode PROJECT=/path/to/app   Install into a specific project"
	@echo "  make uninstall-opencode                      Remove OpenCode install"
	@echo ""
	@echo "Development:"
	@echo "  make test       Run all tests"
	@echo "  make lint       Run linters"
	@echo "  make format     Format code"

.PHONY: install-opencode
install-opencode:
ifdef PROJECT
	@bash "$(CURDIR)/scripts/install-opencode.sh" install --project "$(PROJECT)"
else
	@bash "$(CURDIR)/scripts/install-opencode.sh" install
endif

.PHONY: uninstall-opencode
uninstall-opencode:
ifdef PROJECT
	@bash "$(CURDIR)/scripts/install-opencode.sh" uninstall --project "$(PROJECT)"
else
	@bash "$(CURDIR)/scripts/install-opencode.sh" uninstall
endif

.PHONY: compose-up
compose-up:
	docker compose up --build

.PHONY: compose-down
compose-down:
	docker compose down

.PHONY: seed-users
seed-users:
ifndef USER
	$(error USER is required. Usage: make seed-users USER=peter PASS=changeme)
endif
ifndef PASS
	$(error PASS is required. Usage: make seed-users USER=peter PASS=changeme)
endif
	docker compose exec craic-team-api /app/.venv/bin/python /app/scripts/seed-users.py --username "$(USER)" --password "$(PASS)"

.PHONY: dev-api
dev-api:
	cd team-api && CRAIC_DB_PATH=./dev.db CRAIC_JWT_SECRET=dev-secret uv run craic-team-api

.PHONY: dev-ui
dev-ui:
	cd team-ui && pnpm dev

.PHONY: lint
lint:
	cd plugins/craic/server && uv run ruff check .
	cd plugins/craic/server && uv run ruff format --check .
	cd team-api && uv run ruff check .
	cd team-api && uv run ruff format --check .

.PHONY: format
format:
	cd plugins/craic/server && uv run ruff format .
	cd team-api && uv run ruff format .

.PHONY: format-check
format-check:
	cd plugins/craic/server && uv run ruff format --check .
	cd team-api && uv run ruff format --check .

.PHONY: typecheck
typecheck:
	cd plugins/craic/server && uv sync --group dev && uvx ty check craic_mcp --python .venv
	cd team-api && uv sync --group dev && uvx ty check team_api --python .venv

.PHONY: test
test:
	cd plugins/craic/server && uv sync --group dev && uvx ty check craic_mcp --python .venv
	cd team-api && uv sync --group dev && uvx ty check team_api --python .venv
	cd plugins/craic/server && uv run pytest
	cd team-api && uv run pytest
