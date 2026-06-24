.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "cq - shared agent knowledge commons"
	@echo ""
	@echo "Install cq into a coding agent (requires the cq binary):"
	@echo "  cq install --target <host>                    Install globally"
	@echo "  cq install --target <host> --uninstall        Remove"
	@echo "  cq install --target <host> --dry-run          Preview changes"
	@echo ""
	@echo "  Supported hosts: claude, codex, copilot, cursor, opencode, pi, windsurf"
	@echo ""
	@echo "Development:"
	@echo "  make setup                  Install all dependencies"
	@echo "    - make setup-cli            CLI"
	@echo "    - make setup-schema         Schema (Python package only; Go module needs no setup)"
	@echo "    - make setup-sdk-go         Go SDK"
	@echo "    - make setup-sdk-python     Python SDK"
	@echo "    - make setup-server         Server (backend + frontend)"
	@echo "      - make setup-server-backend  Backend"
	@echo "      - make setup-server-frontend Frontend"
	@echo "  make lint                   Lint all components"
	@echo "    - make lint-cli             CLI"
	@echo "    - make lint-schema          Schema (Go module + Python package)"
	@echo "    - make lint-sdk-go          Go SDK"
	@echo "    - make lint-sdk-python      Python SDK"
	@echo "    - make lint-server          Server (backend + frontend)"
	@echo "      - make lint-server-backend  Backend"
	@echo "      - make lint-server-frontend Frontend"
	@echo "  make test                   Run all tests"
	@echo "    - make test-cli             CLI"
	@echo "    - make test-schema          Schema (Go module + Python package)"
	@echo "    - make test-sdk-go          Go SDK"
	@echo "    - make test-sdk-python      Python SDK"
	@echo "    - make test-server          Server"
	@echo "      - make test-server-backend  Backend"
	@echo "      - make test-server-frontend Frontend"
	@echo "  make sync-prompts           Copy canonical prompts from plugin source to all SDKs"
	@echo "  make check-prompts-sync     Verify all prompt copies match plugin source"
	@echo "    - make check-prompts-sync-sdk-go      Go SDK"
	@echo "    - make check-prompts-sync-sdk-python   Python SDK"
	@echo "  make sync-schema            Copy canonical schemas into the Python schema package"
	@echo "  make validate-schema        Validate JSON Schema fixtures and values file"
	@echo ""
	@echo "Docker Compose:"
	@echo "  make compose-up                              Build and start services (creates .env from example if missing)"
	@echo "  make compose-down                            Stop services"
	@echo "  make compose-reset                           Stop services and wipe database"
	@echo "  make seed-users USER=demo PASS=demo123       Create a user"
	@echo "  make seed-kus   USER=demo PASS=demo123       Load sample knowledge units"
	@echo "  make seed-all   USER=demo PASS=demo123       Create user + load KUs"
	@echo "  make backup-db                               Snapshot server database locally"

.PHONY: setup-cli
setup-cli:
	cd cli && go mod download

.PHONY: setup-schema
setup-schema:
	cd schema && $(MAKE) setup

.PHONY: setup-sdk-go
setup-sdk-go:
	cd sdk/go && $(MAKE) sync-prompts

.PHONY: setup-sdk-python
setup-sdk-python: setup-schema
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
setup: setup-cli setup-schema setup-sdk-go setup-sdk-python setup-server

.PHONY: compose-up
compose-up: .env
	docker compose up --build

.env:
	cp .env.example .env
	@echo "Created .env from .env.example — edit secrets before deploying."

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
	$(error USER is required. Usage: make seed-users USER=demouser PASS=changeme)
endif
ifndef PASS
	$(error PASS is required. Usage: make seed-users USER=demouser PASS=changeme)
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
	docker compose exec cq-server sh -c '/app/.venv/bin/python /app/scripts/seed-kus.py --user "$(USER)" --pass "$(PASS)" --url "http://localhost:$${CQ_PORT:-3000}"'

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
	cd server/backend && CQ_DB_PATH=./dev.db CQ_JWT_SECRET=dev-secret CQ_API_KEY_PEPPER=dev-pepper CQ_PORT=8742 uv run cq-server

.PHONY: dev-ui
dev-ui:
	cd server/frontend && pnpm dev

.PHONY: validate-schema
validate-schema:
	cd schema && $(MAKE) validate

.PHONY: lint-cli
lint-cli:
	cd cli && $(MAKE) lint

.PHONY: lint-schema-go
lint-schema-go:
	cd schema && golangci-lint run --fix -v

.PHONY: lint-schema-python
lint-schema-python: sync-schema
	bash scripts/lint-python-component.sh schema/python

.PHONY: lint-schema
lint-schema: lint-schema-go lint-schema-python

.PHONY: lint-sdk-go
lint-sdk-go: check-prompts-sync-sdk-go
	cd sdk/go && $(MAKE) lint

.PHONY: lint-sdk-python
lint-sdk-python: check-prompts-sync-sdk-python sync-schema
	bash scripts/lint-python-component.sh sdk/python

.PHONY: lint-server-backend
lint-server-backend:
	bash scripts/lint-python-component.sh server/backend

.PHONY: lint-server-frontend
lint-server-frontend:
	bash scripts/lint-frontend.sh

.PHONY: lint-server
lint-server: lint-server-backend lint-server-frontend

.PHONY: sync-prompts
sync-prompts:
	cd sdk/go && $(MAKE) sync-prompts
	cd sdk/python && $(MAKE) sync-prompts

.PHONY: check-prompts-sync-sdk-go
check-prompts-sync-sdk-go:
	cd sdk/go && $(MAKE) check-prompts-sync

.PHONY: check-prompts-sync-sdk-python
check-prompts-sync-sdk-python:
	cd sdk/python && $(MAKE) check-prompts-sync

.PHONY: check-prompts-sync
check-prompts-sync: check-prompts-sync-sdk-go check-prompts-sync-sdk-python

.PHONY: sync-schema
sync-schema:
	cd schema && $(MAKE) sync-schema

.PHONY: lint
lint: check-prompts-sync sync-schema lint-cli lint-schema lint-sdk-go lint-sdk-python lint-server

.PHONY: test-cli
test-cli:
	cd cli && $(MAKE) test

.PHONY: test-schema-go
test-schema-go:
	cd schema && go test ./... -v

.PHONY: test-schema-python
test-schema-python:
	cd schema/python && $(MAKE) test

.PHONY: test-schema
test-schema: test-schema-go test-schema-python

.PHONY: test-sdk-go
test-sdk-go:
	cd sdk/go && $(MAKE) test

.PHONY: test-sdk-python
test-sdk-python:
	cd sdk/python && $(MAKE) test

.PHONY: lint-sdk-go-postgres
lint-sdk-go-postgres:
	cd sdk/go/stores/postgres && $(MAKE) lint

.PHONY: test-sdk-go-postgres
test-sdk-go-postgres:
	cd sdk/go/stores/postgres && $(MAKE) test

.PHONY: test-sdk-python-postgres
test-sdk-python-postgres:
	cd sdk/python && uv run --extra postgres pytest tests/test_store_postgres_conformance.py -v

.PHONY: test-server-backend
test-server-backend: validate-schema
	cd server/backend && uv run pytest

.PHONY: test-server-frontend
test-server-frontend:
	cd server/frontend && pnpm test

.PHONY: test-server
test-server: test-server-backend test-server-frontend

.PHONY: test
test: test-cli test-schema test-sdk-go test-sdk-python test-server
