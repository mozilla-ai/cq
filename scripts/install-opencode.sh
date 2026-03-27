#!/usr/bin/env bash
# Install or uninstall cq for OpenCode.
#
# Usage:
#   install-opencode.sh install [--project <path>]
#   install-opencode.sh uninstall [--project <path>]
#
# Without --project, installs globally to ~/.config/opencode/.
# With --project, installs into <path>/.opencode/.

# shellcheck source=_install-common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_install-common.sh" "$@"

if [[ -n "${PROJECT}" ]]; then
    TARGET="${PROJECT}/.opencode"
else
    TARGET="${HOME}/.config/opencode"
fi

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
# Adds a CQ section between markers so it can be cleanly removed without
# disturbing other content the user or other tools may have added.

CQ_MARKER_START="<!-- cq:start -->"
CQ_MARKER_END="<!-- cq:end -->"

CQ_AGENTS_BLOCK="$(cat <<'BLOCK'
<!-- cq:start -->
## CQ

Before starting any implementation task, load the `cq` skill and follow its Core Protocol.
<!-- cq:end -->
BLOCK
)"

configure_agents_md() {
    local agents_file="${TARGET}/AGENTS.md"

    if [[ -f "${agents_file}" ]]; then
        if grep -qF "${CQ_MARKER_START}" "${agents_file}"; then
            echo "  CQ section already present in ${agents_file}"
        else
            printf '\n%s\n' "${CQ_AGENTS_BLOCK}" >> "${agents_file}"
            echo "  Appended CQ section to ${agents_file}"
        fi
    else
        mkdir -p "$(dirname "${agents_file}")"
        printf '%s\n' "${CQ_AGENTS_BLOCK}" > "${agents_file}"
        echo "  Created ${agents_file} with CQ section"
    fi
}

remove_agents_md() {
    local agents_file="${TARGET}/AGENTS.md"
    [[ -f "${agents_file}" ]] || return 0

    if ! grep -qF "${CQ_MARKER_START}" "${agents_file}"; then
        return 0
    fi

    if ! grep -qF "${CQ_MARKER_END}" "${agents_file}"; then
        echo "  Warning: ${agents_file} has start marker but no end marker — skipping" >&2
        return 0
    fi

    # Remove the CQ section and any trailing blank lines it left behind.
    local tmp
    tmp=$(awk -v start="${CQ_MARKER_START}" -v end="${CQ_MARKER_END}" '
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
        echo "  Removed CQ section from ${agents_file}"
    fi
}

# -- MCP configuration. --

configure_mcp() {
    local config_file="${TARGET}/opencode.json"
    local server_path
    server_path="$(cd "${SERVER_DIR}" && pwd)"

    local cq_entry
    cq_entry=$(jq -n \
        --arg dir "${server_path}" \
        '{ type: "local", command: ["uv", "run", "--directory", $dir, "cq-mcp-server"] }')

    if [[ -f "${config_file}" ]]; then
        if jq -e '.mcp.cq' "${config_file}" &>/dev/null; then
            echo "  MCP server already configured in ${config_file}"
        else
            local tmp
            tmp=$(jq --argjson entry "${cq_entry}" '.mcp.cq = $entry' "${config_file}")
            printf '%s\n' "${tmp}" > "${config_file}"
            echo "  Added CQ MCP server to ${config_file}"
        fi
    else
        mkdir -p "$(dirname "${config_file}")"
        jq -n --argjson entry "${cq_entry}" \
            '{ "$schema": "https://opencode.ai/config.json", mcp: { cq: $entry } }' \
            > "${config_file}"
        echo "  Created ${config_file} with CQ MCP server"
    fi
}

remove_mcp() {
    local config_file="${TARGET}/opencode.json"
    [[ -f "${config_file}" ]] || return 0

    local tmp
    tmp=$(jq 'del(.mcp.cq) | if .mcp == {} then del(.mcp) else . end' "${config_file}")
    printf '%s\n' "${tmp}" > "${config_file}"
    echo "  Removed CQ MCP server from ${config_file}"
}

# -- Dispatch. --

case "${ACTION}" in
    install)
        echo "Installing cq for OpenCode (${TARGET})..."
        apply install "${TARGET}/skills" "skill" "" "${PLUGIN_DIR}"/skills/*/
        generate_commands "${TARGET}/commands"
        configure_mcp
        configure_agents_md
        echo ""
        echo "Done. Restart OpenCode to pick up the changes."
        ;;
    uninstall)
        echo "Removing cq for OpenCode (${TARGET})..."
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
