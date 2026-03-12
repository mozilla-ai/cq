#!/usr/bin/env bash
# Install or uninstall CRAIC for OpenCode.
#
# Usage:
#   install-opencode.sh install [--project <path>]
#   install-opencode.sh uninstall [--project <path>]
#
# Without --project, installs globally to ~/.config/opencode/.
# With --project, installs into <path>/.opencode/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLUGIN_DIR="${REPO_ROOT}/plugins/craic"
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
    TARGET="${PROJECT}/.opencode"
else
    TARGET="${HOME}/.config/opencode"
fi

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

# -- Generate OpenCode command files from Claude Code command files. --
# Strips the `name:` frontmatter field and adds `agent: build`.

generate_commands() {
    local target_dir="$1"
    mkdir -p "${target_dir}"

    for cmd_file in "${PLUGIN_DIR}"/commands/*.md; do
        [[ -f "${cmd_file}" ]] || continue

        local basename
        basename="$(basename "${cmd_file}")"

        awk '
            BEGIN { in_fm=0; past_fm=0 }
            /^---$/ {
                if (!in_fm) { in_fm=1; print; next }
                else { print "agent: build"; print "---"; past_fm=1; next }
            }
            in_fm && /^name:/ { next }
            { print }
        ' "${cmd_file}" > "${target_dir}/${basename}"
        echo "  Generated command: /${basename%.md}"
    done
}

remove_commands() {
    local target_dir="$1"

    for cmd_file in "${PLUGIN_DIR}"/commands/*.md; do
        [[ -f "${cmd_file}" ]] || continue
        local basename
        basename="$(basename "${cmd_file}")"
        if [[ -f "${target_dir}/${basename}" ]]; then
            rm -f "${target_dir}/${basename}"
            echo "  Removed command: /${basename%.md}"
        fi
    done
}

# -- AGENTS.md rules. --
# Adds a CRAIC section between markers so it can be cleanly removed without
# disturbing other content the user or other tools may have added.

CRAIC_MARKER_START="<!-- craic:start -->"
CRAIC_MARKER_END="<!-- craic:end -->"

CRAIC_AGENTS_BLOCK="$(cat <<'BLOCK'
<!-- craic:start -->
## CRAIC

Before starting any implementation task, load the `craic` skill and follow its Core Protocol.
<!-- craic:end -->
BLOCK
)"

configure_agents_md() {
    local agents_file="${TARGET}/AGENTS.md"

    if [[ -f "${agents_file}" ]]; then
        if grep -qF "${CRAIC_MARKER_START}" "${agents_file}"; then
            echo "  CRAIC section already present in ${agents_file}"
        else
            printf '\n%s\n' "${CRAIC_AGENTS_BLOCK}" >> "${agents_file}"
            echo "  Appended CRAIC section to ${agents_file}"
        fi
    else
        mkdir -p "$(dirname "${agents_file}")"
        printf '%s\n' "${CRAIC_AGENTS_BLOCK}" > "${agents_file}"
        echo "  Created ${agents_file} with CRAIC section"
    fi
}

remove_agents_md() {
    local agents_file="${TARGET}/AGENTS.md"
    [[ -f "${agents_file}" ]] || return 0

    if ! grep -qF "${CRAIC_MARKER_START}" "${agents_file}"; then
        return 0
    fi

    if ! grep -qF "${CRAIC_MARKER_END}" "${agents_file}"; then
        echo "  Warning: ${agents_file} has start marker but no end marker — skipping" >&2
        return 0
    fi

    # Remove the CRAIC section and any trailing blank lines it left behind.
    local tmp
    tmp=$(awk -v start="${CRAIC_MARKER_START}" -v end="${CRAIC_MARKER_END}" '
        $0 == start { skip=1; next }
        $0 == end   { skip=0; next }
        skip { next }
        { n++; lines[n] = $0 }
        END {
            # Find last non-blank line.
            last = n
            while (last > 0 && lines[last] ~ /^[[:space:]]*$/) last--
            for (i = 1; i <= last; i++) print lines[i]
        }
    ' "${agents_file}")

    if [[ -z "${tmp}" ]]; then
        rm -f "${agents_file}"
        echo "  Removed ${agents_file} (no other content)"
    else
        printf '%s\n' "${tmp}" > "${agents_file}"
        echo "  Removed CRAIC section from ${agents_file}"
    fi
}

# -- MCP configuration. --

configure_mcp() {
    local config_file="${TARGET}/opencode.json"
    local server_path
    server_path="$(cd "${SERVER_DIR}" && pwd)"

    local craic_entry
    craic_entry=$(jq -n \
        --arg dir "${server_path}" \
        '{ type: "local", command: ["uv", "run", "--directory", $dir, "craic-mcp-server"] }')

    if [[ -f "${config_file}" ]]; then
        if jq -e '.mcp.craic' "${config_file}" &>/dev/null; then
            echo "  MCP server already configured in ${config_file}"
        else
            local tmp
            tmp=$(jq --argjson entry "${craic_entry}" '.mcp.craic = $entry' "${config_file}")
            printf '%s\n' "${tmp}" > "${config_file}"
            echo "  Added CRAIC MCP server to ${config_file}"
        fi
    else
        mkdir -p "$(dirname "${config_file}")"
        jq -n --argjson entry "${craic_entry}" \
            '{ "$schema": "https://opencode.ai/config.json", mcp: { craic: $entry } }' \
            > "${config_file}"
        echo "  Created ${config_file} with CRAIC MCP server"
    fi
}

remove_mcp() {
    local config_file="${TARGET}/opencode.json"
    [[ -f "${config_file}" ]] || return 0

    local tmp
    tmp=$(jq 'del(.mcp.craic) | if .mcp == {} then del(.mcp) else . end' "${config_file}")
    printf '%s\n' "${tmp}" > "${config_file}"
    echo "  Removed CRAIC MCP server from ${config_file}"
}

# -- Dispatch. --

case "${ACTION}" in
    install)
        echo "Installing CRAIC for OpenCode (${TARGET})..."
        apply install "${TARGET}/skills" "skill" "" "${PLUGIN_DIR}"/skills/*/
        generate_commands "${TARGET}/commands"
        configure_mcp
        configure_agents_md
        echo ""
        echo "Done. Restart OpenCode to pick up the changes."
        ;;
    uninstall)
        echo "Removing CRAIC for OpenCode (${TARGET})..."
        apply uninstall "${TARGET}/skills" "skill" "" "${PLUGIN_DIR}"/skills/*/
        remove_commands "${TARGET}/commands"
        remove_mcp
        remove_agents_md
        echo ""
        echo "Done."
        ;;
    *)
        usage
        ;;
esac
