#!/usr/bin/env bash

# Frontend lint: applies Biome's lint + format fixes, then type-checks.
# Auto-fixes locally; CI fails on dirty input via the trailing
# `git diff --exit-code` check.

set -euo pipefail
set -x

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." &>/dev/null && pwd)"
cd "${REPO_ROOT}/server/frontend"
pnpm tsc -b
pnpm lint

git diff --exit-code .
