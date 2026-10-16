# Included by each Go module Makefile. The modfile path resolves relative to this file.
GOLANGCI_LINT_MODFILE := $(dir $(lastword $(MAKEFILE_LIST)))go.mod

# NOTE: GitHub Actions sets CI, so CI verifies and never rewrites the checkout.
# NOTE: Go rejects -modfile in workspace mode, so a local go.work is switched off for the tool build.
.PHONY: golangci-lint
golangci-lint:
	GOWORK=off go tool -modfile=$(GOLANGCI_LINT_MODFILE) golangci-lint run $(if $(CI),,--fix) -v
