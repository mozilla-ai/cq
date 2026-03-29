#!/usr/bin/env bash
# Install or uninstall cq for Cursor.
#
# Usage:
#   install-cursor.sh install [--project <path>]
#   install-cursor.sh uninstall [--project <path>]
#
# Without --project, installs globally to ~/.cursor/.
# With --project, installs into <path>/.cursor/.

# shellcheck source=_install-common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_install-common.sh" "$@"

if [[ -n "${PROJECT}" ]]; then
    TARGET="${PROJECT}/.cursor"
else
    TARGET="${HOME}/.cursor"
fi

# -- MCP configuration. --
# Cursor uses .cursor/mcp.json with a top-level "mcpServers" key.

_shell_quote() {
    printf '%q' "$1"
}

configure_mcp() {
    local config_file="${TARGET}/mcp.json"
    local server_path
    server_path="$(cd "${SERVER_DIR}" && pwd)"

    local cq_entry
    cq_entry=$(jq -n \
        --arg uv "${UV_BIN}" \
        --arg dir "${server_path}" \
        '{ command: $uv, args: ["run", "--directory", $dir, "cq-mcp-server"] }')

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
# Cursor hooks use { "version": 1, "hooks": { ... } }.
# We install a sessionStart hook that syncs the MCP server environment and
# sets session-scoped state, a postToolUseFailure hook that records the last
# failed tool, a postToolUse hook that clears stale failures after recovery,
# and a stop hook that auto-submits a cq follow-up when the agent loop ends
# immediately after a tool failure.

_hook_script() {
    local hook_dir
    hook_dir="$(cd "${PLUGIN_DIR}/hooks/cursor" && pwd)"
    printf '%s' "${hook_dir}/cq_cursor_hook.py"
}

_hook_cmd() {
    local mode="$1"
    local server_path script_path
    server_path="$(cd "${SERVER_DIR}" && pwd)"
    script_path="$(_hook_script)"
    printf '%s --mode %s' \
        "$(_shell_quote "${script_path}")" \
        "$(_shell_quote "${mode}")"
    if [[ "${mode}" == "session-start" ]]; then
        printf ' --server-dir %s --uv-bin %s' \
            "$(_shell_quote "${server_path}")" \
            "$(_shell_quote "${UV_BIN}")"
    fi
}

_legacy_session_start_cmd() {
    local server_path
    server_path="$(cd "${SERVER_DIR}" && pwd)"
    printf 'uv sync --directory %s --quiet' "${server_path}"
}

_ensure_hook() {
    local config_file="$1" hook_name="$2" command="$3" label="$4"
    local hook_entry
    hook_entry=$(jq -n --arg cmd "${command}" '{ command: $cmd }')

    if jq -e --arg hook "${hook_name}" --arg cmd "${command}" \
        '.hooks[$hook][]? | select(.command == $cmd)' "${config_file}" &>/dev/null; then
        echo "  ${label} already configured in ${config_file}"
        return 0
    fi

    local tmp
    tmp=$(jq --arg hook "${hook_name}" --argjson entry "${hook_entry}" '
        .version //= 1 |
        .hooks //= {} |
        .hooks[$hook] //= [] |
        .hooks[$hook] += [$entry]
    ' "${config_file}")
    printf '%s\n' "${tmp}" > "${config_file}"
    echo "  Added ${label} to ${config_file}"
}

_remove_hook() {
    local config_file="$1" hook_name="$2" command="$3" label="$4"
    local tmp
    tmp=$(jq --arg hook "${hook_name}" --arg cmd "${command}" '
        if .hooks[$hook] then
            .hooks[$hook] |= map(select(.command != $cmd))
        else . end |
        if (.hooks[$hook] // []) == [] then del(.hooks[$hook]) else . end |
        if .hooks == {} then del(.hooks) else . end
    ' "${config_file}")
    printf '%s\n' "${tmp}" > "${config_file}"
    echo "  Removed ${label} from ${config_file}"
}

configure_hooks() {
    local config_file="${TARGET}/hooks.json"
    if [[ ! -f "${config_file}" ]]; then
        mkdir -p "$(dirname "${config_file}")"
        jq -n '{ version: 1, hooks: {} }' > "${config_file}"
        echo "  Created ${config_file}"
    fi

    _remove_hook "${config_file}" "sessionStart" "$(_legacy_session_start_cmd)" "legacy session start hook"

    _ensure_hook "${config_file}" "sessionStart" "$(_hook_cmd session-start)" "session start hook"
    _ensure_hook "${config_file}" "postToolUseFailure" "$(_hook_cmd post-tool-use-failure)" "postToolUseFailure hook"
    _ensure_hook "${config_file}" "postToolUse" "$(_hook_cmd post-tool-use)" "postToolUse hook"
    _ensure_hook "${config_file}" "stop" "$(_hook_cmd stop)" "stop hook"
}

remove_hooks() {
    local config_file="${TARGET}/hooks.json"
    [[ -f "${config_file}" ]] || return 0

    _remove_hook "${config_file}" "sessionStart" "$(_legacy_session_start_cmd)" "legacy session start hook"
    _remove_hook "${config_file}" "sessionStart" "$(_hook_cmd session-start)" "session start hook"
    _remove_hook "${config_file}" "postToolUseFailure" "$(_hook_cmd post-tool-use-failure)" "postToolUseFailure hook"
    _remove_hook "${config_file}" "postToolUse" "$(_hook_cmd post-tool-use)" "postToolUse hook"
    _remove_hook "${config_file}" "stop" "$(_hook_cmd stop)" "stop hook"
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
