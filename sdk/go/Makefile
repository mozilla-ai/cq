.DEFAULT_GOAL := help

MODULE_PATH := github.com/mozilla-ai/cq/sdk/go

DIR_NAME := $(subst /,-,$(patsubst %/,%,sdk/go))
VERSION := $(shell \
	tags=$$(git tag -l "sdk/go/*"); \
	if [ -n "$$tags" ]; then \
		git describe --tags --always --dirty --match "sdk/go/*" 2>/dev/null || echo "dev"; \
	else \
		echo "dev"; \
	fi \
)
COMMIT := $(shell git rev-parse HEAD 2>/dev/null || echo "unknown")
DATE := $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")

LDFLAGS := -s -w \
	-X '$(MODULE_PATH)/internal/version.version=$(VERSION)' \
	-X '$(MODULE_PATH)/internal/version.commit=$(COMMIT)' \
	-X '$(MODULE_PATH)/internal/version.date=$(DATE)'

ALLOWED_LICENSES := Apache-2.0,MIT,BSD-2-Clause,BSD-3-Clause,ZeroBSD,Unlicense
NOTICE_TPL := ../../build/licenses/notice.tpl

.PHONY: help
help:
	@echo "cq Go SDK"
	@echo ""
	@echo "  make sync-skill      Copy skill prompt from golden source"
	@echo "  make lint             Run golangci-lint"
	@echo "  make test             Run all tests"
	@echo "  make check-licenses   Verify dependency licenses"
	@echo "  make notice           Regenerate NOTICE from dependency licenses"
	@echo "  make check-notice     Verify NOTICE is up to date"

.PHONY: sync-skill
sync-skill:
	@cp ../../plugins/cq/skills/cq/SKILL.md internal/protocol/skill.md
	@echo "✓ Skill prompt synced."

.PHONY: lint
lint: sync-skill check-notice
	golangci-lint run --fix -v

.PHONY: test
test: lint
	go test ./...

.PHONY: check-licenses
check-licenses:
	@echo "Checking licenses..."
	@go install github.com/google/go-licenses/v2@latest
	@go-licenses check ./... --ignore $(MODULE_PATH) --allowed_licenses=$(ALLOWED_LICENSES)
	@echo "✓ All licenses are allowed."

.PHONY: notice
notice:
	@echo "Generating NOTICE..."
	@go install github.com/google/go-licenses/v2@latest
	@GOOS=linux GOARCH=amd64 go-licenses report ./... --ignore $(MODULE_PATH) --template $(NOTICE_TPL) > NOTICE
	@echo "✓ NOTICE generated."

.PHONY: check-notice
check-notice:
	@echo "Checking NOTICE freshness..."
	@go install github.com/google/go-licenses/v2@latest
	@GOOS=linux GOARCH=amd64 go-licenses report ./... --ignore $(MODULE_PATH) --template $(NOTICE_TPL) > NOTICE.tmp
	@diff -q NOTICE NOTICE.tmp > /dev/null 2>&1 || (echo "NOTICE is stale. Run 'make notice' to regenerate." && rm -f NOTICE.tmp && exit 1)
	@rm -f NOTICE.tmp
	@echo "✓ NOTICE is up to date."
