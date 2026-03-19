.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "cq - shared agent knowledge commons"
	@echo ""
	@echo "Claude Code (recommended):"
	@echo "  claude plugin marketplace add mozilla-ai/cq"
	@echo "  claude plugin install cq"
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
	@echo ""
	@echo "Docker Compose:"
	@echo "  make compose-up                              Build and start services"
	@echo "  make compose-down                            Stop services"
	@echo "  make compose-reset                           Stop services and wipe database"
	@echo "  make seed-users USER=demo PASS=demo123       Create a user"
	@echo "  make seed-kus   USER=demo PASS=demo123       Load sample knowledge units"
	@echo "  make seed-all   USER=demo PASS=demo123       Create user + load KUs"

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

.PHONY: lint
lint:
	cd plugins/cq/server && uv run ruff check .
	cd plugins/cq/server && uv run ruff format --check .
	cd team-api && uv run ruff check .
	cd team-api && uv run ruff format --check .
	cd team-ui && pnpm tsc -b
	cd team-ui && pnpm lint

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

.PHONY: test
test:
	cd plugins/cq/server && uv sync --group dev && uvx ty check cq_mcp --python .venv
	cd team-api && uv sync --group dev && uvx ty check team_api --python .venv
	cd plugins/cq/server && uv run pytest
	cd team-api && uv run pytest
