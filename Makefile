.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "cq - shared agent knowledge commons"
	@echo ""
	@echo "Claude Code (recommended):"
	@echo "  make install-claude                          Install cq plugin"
	@echo "  make uninstall-claude                        Remove cq plugin"
	@echo ""
	@echo "OpenCode:"
	@echo "  make install-opencode                        Install globally (~/.config/opencode/)"
	@echo "  make install-opencode PROJECT=/path/to/app   Install into a specific project"
	@echo "  make uninstall-opencode                      Remove global OpenCode install"
	@echo "  make uninstall-opencode PROJECT=/path/to/app Remove from a specific project"
	@echo ""
	@echo "Development:"
	@echo "  make setup     Install all dependencies"
	@echo "  make test              Run all tests"
	@echo "  make lint              Format, lint, and type-check all components"
	@echo "  make validate-schema   Validate JSON Schema fixtures"
	@echo ""
	@echo "Docker Compose:"
	@echo "  make compose-up                              Build and start services"
	@echo "  make compose-down                            Stop services"
	@echo "  make compose-reset                           Stop services and wipe database"
	@echo "  make seed-users USER=demo PASS=demo123       Create a user"
	@echo "  make seed-kus   USER=demo PASS=demo123       Load sample knowledge units"
	@echo "  make seed-all   USER=demo PASS=demo123       Create user + load KUs"

.PHONY: setup
setup:
	(cd sdk/python && uv sync --group dev)
	(cd plugins/cq/server && uv sync --group dev)
	(cd team-api && uv sync --group dev)
	(cd team-ui && pnpm install $(if $(CI),--frozen-lockfile,))

.PHONY: install-claude
install-claude:
	claude plugin marketplace add mozilla-ai/cq
	claude plugin install cq

.PHONY: uninstall-claude
uninstall-claude:
	claude plugin marketplace remove mozilla-ai/cq

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

.PHONY: compose-reset
compose-reset:
	docker compose down -v

.PHONY: seed-users
seed-users:
ifndef USER
	$(error USER is required. Usage: make seed-users USER=peter PASS=changeme)
endif
ifndef PASS
	$(error PASS is required. Usage: make seed-users USER=peter PASS=changeme)
endif
	docker compose exec cq-team-api /app/.venv/bin/python /app/scripts/seed-users.py --username "$(USER)" --password "$(PASS)"

.PHONY: seed-kus
seed-kus:
ifndef USER
	$(error USER is required. Usage: make seed-kus USER=demo PASS=demo123)
endif
ifndef PASS
	$(error PASS is required. Usage: make seed-kus USER=demo PASS=demo123)
endif
	docker compose exec cq-team-api /app/.venv/bin/python /app/scripts/seed/load.py --user "$(USER)" --pass "$(PASS)" --url http://localhost:8742

.PHONY: seed-all
seed-all:
ifndef USER
	$(error USER is required. Usage: make seed-all USER=demo PASS=demo123)
endif
ifndef PASS
	$(error PASS is required. Usage: make seed-all USER=demo PASS=demo123)
endif
	$(MAKE) seed-users USER="$(USER)" PASS="$(PASS)"
	$(MAKE) seed-kus USER="$(USER)" PASS="$(PASS)"

.PHONY: dev-api
dev-api:
	cd team-api && CQ_DB_PATH=./dev.db CQ_JWT_SECRET=dev-secret uv run cq-team-api

.PHONY: dev-ui
dev-ui:
	cd team-ui && pnpm dev

.PHONY: validate-schema
validate-schema:
	cd schema && $(MAKE) validate

.PHONY: lint
lint:
	cd plugins/cq/server && uv run pre-commit run --all-files --config "$(CURDIR)/.pre-commit-config.yaml"
	bash scripts/lint-frontend.sh

.PHONY: format
format:
	cd plugins/cq/server && uv run ruff format .
	cd team-api && uv run ruff format .

.PHONY: format-check
format-check:
	cd plugins/cq/server && uv run ruff format --check .
	cd team-api && uv run ruff format --check .

.PHONY: typecheck
typecheck:
	cd plugins/cq/server && uv sync --group dev && uvx ty check cq_mcp --python .venv
	cd team-api && uv sync --group dev && uvx ty check team_api --python .venv
	cd team-ui && pnpm tsc -b

.PHONY: test-python-sdk
test-python-sdk:
	cd sdk/python && $(MAKE) test

.PHONY: test
test: validate-schema test-python-sdk
	cd plugins/cq/server && uv sync --group dev && uvx ty check cq_mcp --python .venv
	cd team-api && uv sync --group dev && uvx ty check team_api --python .venv
	cd plugins/cq/server && uv run pytest
	cd team-api && uv run pytest
