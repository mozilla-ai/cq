#!/usr/bin/env bash

# Frontend lint: applies Biome's lint + format fixes, then type-checks.
# Auto-fixes locally; in CI, fails on dirty input via the trailing
# `git diff --exit-code` check so unformatted commits cannot land.

set -euo pipefail
set -x

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." &>/dev/null && pwd)"
cd "${REPO_ROOT}/server/frontend"
pnpm lint
pnpm tsc -b

if [[ "${CI:-}" == "true" ]]; then
  git diff --exit-code .
fi
