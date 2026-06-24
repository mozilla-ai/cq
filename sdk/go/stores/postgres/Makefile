.DEFAULT_GOAL := help

MODULE_PATH := github.com/mozilla-ai/cq/sdk/go/stores/postgres
ALLOWED_LICENSES := Apache-2.0,MIT,BSD-2-Clause,BSD-3-Clause,ZeroBSD,Unlicense
NOTICE_TPL := ../../../../build/licenses/notice.tpl
SDK_MODULE_PATH := github.com/mozilla-ai/cq/sdk/go
SCHEMA_MODULE_PATH := github.com/mozilla-ai/cq/schema

.PHONY: help
help:
	@echo "cq Go SDK — PostgreSQL Store adapter"
	@echo ""
	@echo "  make lint             Run golangci-lint"
	@echo "  make test             Run all tests"
	@echo "  make check-licenses   Verify dependency licenses"
	@echo "  make notice           Regenerate NOTICE from dependency licenses"
	@echo "  make check-notice     Verify NOTICE is up to date"

.PHONY: lint
lint: check-notice check-licenses
	golangci-lint run --fix -v

.PHONY: test
test:
	go test ./... -v

.PHONY: check-licenses
check-licenses:
	@echo "Checking licenses..."
	@go install github.com/google/go-licenses/v2@latest
	@go-licenses check ./... --ignore $(MODULE_PATH) --ignore $(SDK_MODULE_PATH) --ignore $(SCHEMA_MODULE_PATH) --allowed_licenses=$(ALLOWED_LICENSES)
	@echo "✓ All licenses are allowed."

.PHONY: notice
notice:
	@echo "Generating NOTICE..."
	@go install github.com/google/go-licenses/v2@latest
	@GOOS=linux GOARCH=amd64 go-licenses report ./... --ignore $(MODULE_PATH) --ignore $(SDK_MODULE_PATH) --ignore $(SCHEMA_MODULE_PATH) --template $(NOTICE_TPL) > NOTICE
	@echo "✓ NOTICE generated."

.PHONY: check-notice
check-notice:
	@echo "Checking NOTICE freshness..."
	@go install github.com/google/go-licenses/v2@latest
	@GOOS=linux GOARCH=amd64 go-licenses report ./... --ignore $(MODULE_PATH) --ignore $(SDK_MODULE_PATH) --ignore $(SCHEMA_MODULE_PATH) --template $(NOTICE_TPL) > NOTICE.tmp
	@diff -q NOTICE NOTICE.tmp > /dev/null 2>&1 || (echo "NOTICE is stale. Run 'make notice' to regenerate." && rm -f NOTICE.tmp && exit 1)
	@rm -f NOTICE.tmp
	@echo "✓ NOTICE is up to date."
