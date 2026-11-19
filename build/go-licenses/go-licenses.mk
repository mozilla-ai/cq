# Included by each Go module Makefile. The modfile path resolves relative to this file.
GO_LICENSES_MODFILE := $(dir $(lastword $(MAKEFILE_LIST)))go.mod

# NOTE: Go rejects -modfile in workspace mode, so a local go.work is switched off for the tool build.
# NOTE: The tool is built here, not under the recipe's GOOS/GOARCH, so the binary still runs on the host.
# NOTE: Resolution is lazy (recursive =), so unrelated targets never build the tool. An empty result stops make before a recipe can truncate NOTICE.
GO_LICENSES_BIN = $(or $(shell GOWORK=off go tool -modfile=$(GO_LICENSES_MODFILE) -n go-licenses),$(error go-licenses: tool resolution failed))
# NOTE: Quoted so a cache path containing spaces stays one shell word.
GO_LICENSES = "$(GO_LICENSES_BIN)"
