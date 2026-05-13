#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <component-dir>" >&2
  exit 1
fi

component_dir="$1"

if [[ ! -d "$component_dir" ]]; then
  echo "Component directory not found: $component_dir" >&2
  exit 1
fi

git -C "$component_dir" ls-files -z --cached --others --exclude-standard -- \
  '*.py' \
  'pyproject.toml' \
  'uv.lock' | \
  xargs -0 -I{} printf '%s/%s\0' "$component_dir" "{}" | \
  xargs -0 uv run --project "$component_dir" --locked pre-commit run --files
