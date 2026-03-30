.DEFAULT_GOAL := help

MODULE_PATH := github.com/mozilla-ai/cq/cli

VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
COMMIT := $(shell git rev-parse HEAD 2>/dev/null || echo "unknown")
DATE := $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")

LDFLAGS := -s -w \
	-X '$(MODULE_PATH)/internal/version.version=$(VERSION)' \
	-X '$(MODULE_PATH)/internal/version.commit=$(COMMIT)' \
	-X '$(MODULE_PATH)/internal/version.date=$(DATE)'

BUILDFLAGS := -trimpath

.PHONY: help
help:
	@echo "cq CLI"
	@echo ""
	@echo "  make build     Build the cq binary"
	@echo "  make lint      Run golangci-lint"
	@echo "  make test      Run all tests"
	@echo "  make install   Copy binary to /usr/local/bin"

.PHONY: lint
lint:
	golangci-lint run --fix -v

.PHONY: test
test: lint
	go test ./...

.PHONY: build
build: lint
	@echo "Building cq (version: $(VERSION), commit: $(COMMIT))..."
	@go build $(BUILDFLAGS) -o cq -ldflags="$(LDFLAGS)" .

.PHONY: install
install: build
	@cp cq /usr/local/bin/cq
	@chmod +x /usr/local/bin/cq

.PHONY: clean
clean:
	@rm -f cq
