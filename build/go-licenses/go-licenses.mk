# Included by each Go module Makefile. The modfile path resolves relative to this file.
GO_LICENSES_MODFILE := $(dir $(lastword $(MAKEFILE_LIST)))go.mod

# NOTE: Go rejects -modfile in workspace mode, so a local go.work is switched off for the tool build.
# NOTE: The tool is built here, not under the recipe's GOOS/GOARCH, so the binary still runs on the host.
GO_LICENSES = $(shell GOWORK=off go tool -modfile=$(GO_LICENSES_MODFILE) -n go-licenses)
