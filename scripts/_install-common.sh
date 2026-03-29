#!/usr/bin/env bash
# Shared helpers for cq install scripts.
# Sourced by install-cursor.sh and install-opencode.sh.
#
# Provides: SCRIPT_DIR, REPO_ROOT, PLUGIN_DIR, SERVER_DIR, ACTION, PROJECT,
#           UV_BIN, apply(), usage(), and dependency checks.
#
# The sourcing script must set TARGET after sourcing this file.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLUGIN_DIR="${REPO_ROOT}/plugins/cq"
SERVER_DIR="${PLUGIN_DIR}/server"

# -- Dependencies. --

if ! command -v jq &>/dev/null; then
    echo "Error: jq is required. Install with: brew install jq" >&2
    exit 1
fi

UV_BIN="$(command -v uv || true)"
if [[ -z "${UV_BIN}" ]]; then
    echo "Error: uv is required. Install from: https://docs.astral.sh/uv/" >&2
    exit 1
fi

# -- Argument parsing. --

usage() {
    echo "Usage: $(basename "${BASH_SOURCE[1]}") <install|uninstall> [--project <path>]"
    exit 1
}

if [[ $# -lt 1 ]]; then
    usage
fi

ACTION="$1"
shift
PROJECT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project)
            PROJECT="${2:?--project requires a path}"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            ;;
    esac
done

# -- Core: apply an action to a set of sources. --
# Usage: apply <install|uninstall> <target_dir> <label> <strip_ext> <sources...>
# Sources are pre-expanded by the caller (glob expansion happens at call site).

apply() {
    local action="$1" target_dir="$2" label="$3" strip_ext="$4"
    shift 4

    [[ "${action}" == "install" ]] && mkdir -p "${target_dir}"

    for src in "$@"; do
        [[ -e "${src}" ]] || continue
        local name
        name="$(basename "${src}" "${strip_ext}")"

        if [[ "${action}" == "install" ]]; then
            if [[ -d "${src}" ]]; then
                ln -sfn "${src}" "${target_dir}/$(basename "${src}")"
            else
                ln -sf "${src}" "${target_dir}/"
            fi
            echo "  Linked ${label}: ${name}"
        else
            rm -rf "${target_dir}/$(basename "${src}")"
            echo "  Removed ${label}: ${name}"
        fi
    done
}
