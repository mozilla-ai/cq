.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "cq - shared agent knowledge commons"
	@echo ""
	@echo "Claude Code (recommended):"
	@echo "  make install-claude                          Install cq plugin via Claude marketplace"
	@echo "  make uninstall-claude                        Remove cq plugin via Claude marketplace"
	@echo ""
	@echo "OpenCode:"
	@echo "  make install-opencode                        Install globally (~/.config/opencode/)"
	@echo "  make install-opencode PROJECT=/path/to/app   Install into a specific project"
	@echo "  make uninstall-opencode                      Remove global OpenCode install"
	@echo "  make uninstall-opencode PROJECT=/path/to/app Remove from a specific project"
	@echo ""
	@echo "Cursor:"
	@echo "  make install-cursor                          Install globally (~/.cursor/)"
	@echo "  make install-cursor PROJECT=/path/to/app     Install into a specific project"
	@echo "  make uninstall-cursor                        Remove global Cursor install"
	@echo "  make uninstall-cursor PROJECT=/path/to/app   Remove from a specific project"
	@echo ""
	@echo "Windsurf:"
	@echo "  make install-windsurf                        Install globally (~/.codeium/windsurf/)"
	@echo "  make uninstall-windsurf                      Remove global Windsurf install"
	@echo ""
	@echo "All hosts at once:"
	@echo "  make install-all                             Install every host globally"
	@echo "  make install-all PROJECT=/path/to/app        Install every project-capable host into a project"
	@echo ""
	@echo "Development:"
	@echo "  make setup                  Install all dependencies"
	@echo "    - make setup-cli            CLI"
	@echo "    - make setup-install        Multi-host installer"
	@echo "    - make setup-plugin         Plugin"
	@echo "    - make setup-sdk-go         Go SDK"
	@echo "    - make setup-sdk-python     Python SDK"
	@echo "    - make setup-server         Server (backend + frontend)"
	@echo "      - make setup-server-backend  Backend"
	@echo "      - make setup-server-frontend Frontend"
	@echo "  make lint                   Lint all components"
	@echo "    - make lint-cli             CLI"
	@echo "    - make lint-install         Multi-host installer"
	@echo "    - make lint-plugin          Plugin"
	@echo "    - make lint-sdk-go          Go SDK"
	@echo "    - make lint-sdk-python      Python SDK"
	@echo "    - make lint-server          Server (backend + frontend)"
	@echo "      - make lint-server-backend  Backend"
	@echo "      - make lint-server-frontend Frontend"
	@echo "  make test                   Run all tests"
	@echo "    - make test-cli             CLI"
	@echo "    - make test-install         Multi-host installer"
	@echo "    - make test-plugin          Plugin (Cursor hook helper)"
	@echo "    - make test-sdk-go          Go SDK"
	@echo "    - make test-sdk-python      Python SDK"
	@echo "    - make test-server          Server"
	@echo "      - make test-server-backend  Backend"
	@echo "      - make test-server-frontend Frontend"
	@echo "  make validate-schema        Validate JSON Schema fixtures"
	@echo ""
	@echo "Docker Compose:"
	@echo "  make compose-up                              Build and start services"
	@echo "  make compose-down                            Stop services"
	@echo "  make compose-reset                           Stop services and wipe database"
	@echo "  make seed-users USER=demo PASS=demo123       Create a user"
	@echo "  make seed-kus   USER=demo PASS=demo123       Load sample knowledge units"
	@echo "  make seed-all   USER=demo PASS=demo123       Create user + load KUs"
	@echo "  make backup-db                               Snapshot server database locally"

.PHONY: setup-cli
setup-cli:
	cd cli && go mod download

.PHONY: setup-install
setup-install:
	cd scripts/install && uv sync --group dev

.PHONY: setup-plugin
setup-plugin:
	cd plugins/cq && uv sync --group dev

.PHONY: setup-sdk-go
setup-sdk-go:
	cd sdk/go && $(MAKE) sync-skill

.PHONY: setup-sdk-python
setup-sdk-python:
	cd sdk/python && uv sync --group dev

.PHONY: setup-server-backend
setup-server-backend:
	cd server/backend && uv sync --group dev

.PHONY: setup-server-frontend
setup-server-frontend:
	cd server/frontend && pnpm install $(if $(CI),--frozen-lockfile,)

.PHONY: setup-server
setup-server: setup-server-backend setup-server-frontend

.PHONY: setup
setup: setup-cli setup-install setup-plugin setup-sdk-go setup-sdk-python setup-server

.PHONY: install-claude
install-claude:
	cd scripts/install && uv run python -m cq_install install --target claude

.PHONY: uninstall-claude
uninstall-claude:
	cd scripts/install && uv run python -m cq_install uninstall --target claude

.PHONY: install-cursor
install-cursor:
ifdef PROJECT
	cd scripts/install && uv run python -m cq_install install --target cursor --project "$(PROJECT)"
else
	cd scripts/install && uv run python -m cq_install install --target cursor --global
endif

.PHONY: uninstall-cursor
uninstall-cursor:
ifdef PROJECT
	cd scripts/install && uv run python -m cq_install uninstall --target cursor --project "$(PROJECT)"
else
	cd scripts/install && uv run python -m cq_install uninstall --target cursor --global
endif

.PHONY: install-opencode
install-opencode:
ifdef PROJECT
	cd scripts/install && uv run python -m cq_install install --target opencode --project "$(PROJECT)"
else
	cd scripts/install && uv run python -m cq_install install --target opencode --global
endif

.PHONY: uninstall-opencode
uninstall-opencode:
ifdef PROJECT
	cd scripts/install && uv run python -m cq_install uninstall --target opencode --project "$(PROJECT)"
else
	cd scripts/install && uv run python -m cq_install uninstall --target opencode --global
endif

.PHONY: install-windsurf
install-windsurf:
ifdef PROJECT
	@echo "Note: Windsurf has no per-project MCP config; installing globally and ignoring PROJECT=$(PROJECT)."
endif
	cd scripts/install && uv run python -m cq_install install --target windsurf --global

.PHONY: uninstall-windsurf
uninstall-windsurf:
ifdef PROJECT
	@echo "Note: Windsurf has no per-project MCP config; uninstalling globally and ignoring PROJECT=$(PROJECT)."
endif
	cd scripts/install && uv run python -m cq_install uninstall --target windsurf --global

.PHONY: install-all
install-all:
ifdef PROJECT
	cd scripts/install && uv run python -m cq_install install --target opencode --target cursor --target claude --project "$(PROJECT)"
	@echo "Note: Windsurf has no per-project MCP config; installing it globally."
	cd scripts/install && uv run python -m cq_install install --target windsurf --global
else
	cd scripts/install && uv run python -m cq_install install --target opencode --target cursor --target windsurf --target claude --global
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

.PHONY: backup-db
backup-db:
	@bash server/scripts/backup-db.sh

.PHONY: seed-users
seed-users:
ifndef USER
	$(error USER is required. Usage: make seed-users USER=peter PASS=changeme)
endif
ifndef PASS
	$(error PASS is required. Usage: make seed-users USER=peter PASS=changeme)
endif
	docker compose exec cq-server /app/.venv/bin/python /app/scripts/seed-users.py --username "$(USER)" --password "$(PASS)"

.PHONY: seed-kus
seed-kus:
ifndef USER
	$(error USER is required. Usage: make seed-kus USER=demo PASS=demo123)
endif
ifndef PASS
	$(error PASS is required. Usage: make seed-kus USER=demo PASS=demo123)
endif
	docker compose exec cq-server /app/.venv/bin/python /app/scripts/seed-kus.py --user "$(USER)" --pass "$(PASS)" --url http://localhost:3000

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
	cd server/backend && CQ_DB_PATH=./dev.db CQ_JWT_SECRET=dev-secret CQ_PORT=8742 uv run cq-server

.PHONY: dev-ui
dev-ui:
	cd server/frontend && pnpm dev

.PHONY: validate-schema
validate-schema:
	cd schema && $(MAKE) validate

.PHONY: lint-cli
lint-cli:
	cd cli && $(MAKE) lint

.PHONY: lint-install
lint-install:
	cd scripts/install && uv run --locked pre-commit run --files src/**/*.py tests/*.py pyproject.toml uv.lock

.PHONY: lint-plugin
lint-plugin:
	cd plugins/cq && uv run --locked pre-commit run --files scripts/*.py pyproject.toml uv.lock

.PHONY: lint-sdk-go
lint-sdk-go:
	cd sdk/go && $(MAKE) lint

.PHONY: lint-sdk-python
lint-sdk-python:
	cd sdk/python && uv run --locked pre-commit run --files src/**/*.py pyproject.toml uv.lock

.PHONY: lint-server-backend
lint-server-backend:
	cd server/backend && uv run --locked pre-commit run --files src/**/*.py pyproject.toml uv.lock

.PHONY: lint-server-frontend
lint-server-frontend:
	bash scripts/lint-frontend.sh

.PHONY: lint-server
lint-server: lint-server-backend lint-server-frontend

.PHONY: lint
lint: lint-cli lint-install lint-plugin lint-sdk-go lint-sdk-python lint-server

.PHONY: test-cli
test-cli:
	cd cli && $(MAKE) test

.PHONY: test-install
test-install:
	cd scripts/install && uv run pytest

.PHONY: test-plugin
test-plugin:
	cd plugins/cq && uv run pytest

.PHONY: test-sdk-go
test-sdk-go:
	cd sdk/go && $(MAKE) test

.PHONY: test-sdk-python
test-sdk-python:
	cd sdk/python && $(MAKE) test

.PHONY: test-server-backend
test-server-backend: validate-schema
	cd server/backend && uv run pytest

.PHONY: test-server-frontend
test-server-frontend:
	cd server/frontend && pnpm test

.PHONY: test-server
test-server: test-server-backend test-server-frontend

.PHONY: test
test: test-cli test-install test-plugin test-sdk-go test-sdk-python test-server
