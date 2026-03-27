#!/usr/bin/env bash
# Install or uninstall cq for Cursor.
#
# Usage:
#   install-cursor.sh install [--project <path>]
#   install-cursor.sh uninstall [--project <path>]
#
# Without --project, installs globally to ~/.cursor/.
# With --project, installs into <path>/.cursor/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLUGIN_DIR="${REPO_ROOT}/plugins/cq"
SERVER_DIR="${PLUGIN_DIR}/server"

# -- Dependencies. --

if ! command -v jq &>/dev/null; then
    echo "Error: jq is required. Install with: brew install jq" >&2
    exit 1
fi

# -- Argument parsing. --

usage() {
    echo "Usage: $(basename "$0") <install|uninstall> [--project <path>]"
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

if [[ -n "${PROJECT}" ]]; then
    TARGET="${PROJECT}/.cursor"
else
    TARGET="${HOME}/.cursor"
fi

# -- Core: apply an action to a set of sources. --
# Usage: apply <install|uninstall> <target_dir> <label> <strip_ext> <sources...>

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

# -- MCP configuration. --
# Cursor uses .cursor/mcp.json with a top-level "mcpServers" key.

configure_mcp() {
    local config_file="${TARGET}/mcp.json"
    local server_path
    server_path="$(cd "${SERVER_DIR}" && pwd)"

    local cq_entry
    cq_entry=$(jq -n \
        --arg dir "${server_path}" \
        '{ command: "uv", args: ["run", "--directory", $dir, "cq-mcp-server"] }')

    if [[ -f "${config_file}" ]]; then
        if jq -e '.mcpServers.cq' "${config_file}" &>/dev/null; then
            echo "  MCP server already configured in ${config_file}"
        else
            local tmp
            tmp=$(jq --argjson entry "${cq_entry}" '.mcpServers.cq = $entry' "${config_file}")
            printf '%s\n' "${tmp}" > "${config_file}"
            echo "  Added cq MCP server to ${config_file}"
        fi
    else
        mkdir -p "$(dirname "${config_file}")"
        jq -n --argjson entry "${cq_entry}" \
            '{ mcpServers: { cq: $entry } }' \
            > "${config_file}"
        echo "  Created ${config_file} with cq MCP server"
    fi
}

remove_mcp() {
    local config_file="${TARGET}/mcp.json"
    [[ -f "${config_file}" ]] || return 0

    local tmp
    tmp=$(jq 'del(.mcpServers.cq) | if .mcpServers == {} then del(.mcpServers) else . end' "${config_file}")
    printf '%s\n' "${tmp}" > "${config_file}"
    echo "  Removed cq MCP server from ${config_file}"
}

# -- Hooks configuration. --
# Cursor hooks use { "version": 1, "hooks": { "sessionStart": [...] } }.
# We add a sessionStart hook to pre-sync the MCP server's Python dependencies.

_hook_cmd() {
    local server_path
    server_path="$(cd "${SERVER_DIR}" && pwd)"
    echo "uv sync --directory ${server_path} --quiet"
}

configure_hooks() {
    local config_file="${TARGET}/hooks.json"
    local hook_cmd
    hook_cmd="$(_hook_cmd)"

    local cq_hook
    cq_hook=$(jq -n --arg cmd "${hook_cmd}" '{ command: $cmd }')

    if [[ -f "${config_file}" ]]; then
        if jq -e --arg cmd "${hook_cmd}" '.hooks.sessionStart[]? | select(.command == $cmd)' "${config_file}" &>/dev/null; then
            echo "  Session start hook already configured in ${config_file}"
        else
            local tmp
            tmp=$(jq --argjson entry "${cq_hook}" '
                .version //= 1 |
                .hooks //= {} |
                .hooks.sessionStart //= [] |
                .hooks.sessionStart += [$entry]
            ' "${config_file}")
            printf '%s\n' "${tmp}" > "${config_file}"
            echo "  Added session start hook to ${config_file}"
        fi
    else
        mkdir -p "$(dirname "${config_file}")"
        jq -n --argjson entry "${cq_hook}" '{
            version: 1,
            hooks: {
                sessionStart: [$entry]
            }
        }' > "${config_file}"
        echo "  Created ${config_file} with session start hook"
    fi
}

remove_hooks() {
    local config_file="${TARGET}/hooks.json"
    [[ -f "${config_file}" ]] || return 0

    local hook_cmd
    hook_cmd="$(_hook_cmd)"

    local tmp
    tmp=$(jq --arg cmd "${hook_cmd}" '
        if .hooks.sessionStart then
            .hooks.sessionStart |= map(select(.command != $cmd))
        else . end |
        if (.hooks.sessionStart // []) == [] then del(.hooks.sessionStart) else . end |
        if .hooks == {} then del(.hooks) else . end
    ' "${config_file}")
    printf '%s\n' "${tmp}" > "${config_file}"
    echo "  Removed session start hook from ${config_file}"
}

# -- Rule configuration. --
# Creates an agent-decided .cursor/rules/cq.mdc rule that directs the
# agent to load the cq skill. Cursor auto-discovers skills from
# .cursor/skills/, so this rule provides an additional prompt-level nudge.

CQ_RULE_CONTENT='---
description: Shared knowledge commons for AI agents. Query before unfamiliar work (APIs, CI/CD, build tools, frameworks). Propose when you discover something non-obvious.
alwaysApply: false
---

Before starting any implementation task, load the `cq` skill and follow its Core Protocol.'

configure_rule() {
    local rules_dir="${TARGET}/rules"
    local rule_file="${rules_dir}/cq.mdc"

    mkdir -p "${rules_dir}"

    if [[ -f "${rule_file}" ]]; then
        echo "  Rule already exists at ${rule_file}"
    else
        printf '%s\n' "${CQ_RULE_CONTENT}" > "${rule_file}"
        echo "  Created rule: cq.mdc"
    fi
}

remove_rule() {
    local rule_file="${TARGET}/rules/cq.mdc"
    if [[ -f "${rule_file}" ]]; then
        rm -f "${rule_file}"
        echo "  Removed rule: cq.mdc"
    fi
}

# -- Dispatch. --

case "${ACTION}" in
    install)
        echo "Installing cq for Cursor (${TARGET})..."
        apply install "${TARGET}/skills" "skill" "" "${PLUGIN_DIR}"/skills/*/
        configure_mcp
        configure_hooks
        configure_rule
        echo ""
        echo "Done. Restart Cursor to pick up the changes."
        ;;
    uninstall)
        echo "Removing cq for Cursor (${TARGET})..."
        apply uninstall "${TARGET}/skills" "skill" "" "${PLUGIN_DIR}"/skills/*/
        remove_mcp
        remove_hooks
        remove_rule
        echo ""
        echo "Done."
        ;;
    *)
        usage
        ;;
esac
