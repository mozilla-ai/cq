#!/usr/bin/env bash
# Tests for install-opencode.sh.
#
# Runs against a temp directory to avoid touching real config.
# Exits non-zero on first failure.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL="${SCRIPT_DIR}/install-opencode.sh"
PLUGIN_DIR="$(cd "${SCRIPT_DIR}/../plugins/cq" && pwd)"
BOOTSTRAP="${PLUGIN_DIR}/scripts/bootstrap.py"

TMPDIR_ROOT="$(mktemp -d)"
trap 'rm -rf "${TMPDIR_ROOT}"' EXIT

PASS=0
FAIL=0

assert_eq() {
    local label="$1" expected="$2" actual="$3"
    if [[ "${expected}" == "${actual}" ]]; then
        echo "  PASS: ${label}"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: ${label}"
        echo "    expected: ${expected}"
        echo "    actual:   ${actual}"
        FAIL=$((FAIL + 1))
    fi
}

assert_contains() {
    local label="$1" needle="$2" haystack="$3"
    if [[ "${haystack}" == *"${needle}"* ]]; then
        echo "  PASS: ${label}"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: ${label}"
        echo "    expected to contain: ${needle}"
        echo "    actual:              ${haystack}"
        FAIL=$((FAIL + 1))
    fi
}

assert_not_exists() {
    local label="$1" path="$2"
    if [[ ! -e "${path}" ]]; then
        echo "  PASS: ${label}"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: ${label} (file should not exist: ${path})"
        FAIL=$((FAIL + 1))
    fi
}

assert_exists() {
    local label="$1" path="$2"
    if [[ -e "${path}" ]]; then
        echo "  PASS: ${label}"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: ${label} (file should exist: ${path})"
        FAIL=$((FAIL + 1))
    fi
}

assert_symlink() {
    local label="$1" path="$2" target="$3"
    if [[ -L "${path}" ]]; then
        local actual
        actual="$(readlink "${path}")"
        assert_eq "${label}" "${target}" "${actual}"
    else
        echo "  FAIL: ${label} (not a symlink: ${path})"
        FAIL=$((FAIL + 1))
    fi
}

# ── Fresh install ────────────────────────────────────────────────────

echo "=== Test: fresh install ==="

PROJECT="${TMPDIR_ROOT}/fresh"
mkdir -p "${PROJECT}"
bash "${INSTALL}" install --project "${PROJECT}" >/dev/null

TARGET="${PROJECT}/.opencode"

# Skills.
assert_symlink "skill symlink" "${TARGET}/skills/cq" "${PLUGIN_DIR}/skills/cq/"

# Commands.
assert_exists "cq-reflect command" "${TARGET}/commands/cq-reflect.md"
assert_exists "cq-status command" "${TARGET}/commands/cq-status.md"

# Command frontmatter: name stripped, agent added.
if grep -q '^name:' "${TARGET}/commands/cq-reflect.md"; then
    echo "  FAIL: cq-reflect should not have name: in frontmatter"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: cq-reflect name: stripped"
    PASS=$((PASS + 1))
fi
if grep -q '^agent: build' "${TARGET}/commands/cq-reflect.md"; then
    echo "  PASS: cq-reflect has agent: build"
    PASS=$((PASS + 1))
else
    echo "  FAIL: cq-reflect should have agent: build in frontmatter"
    FAIL=$((FAIL + 1))
fi

# MCP config.
assert_exists "opencode.json exists" "${TARGET}/opencode.json"
mcp_cmd=$(jq -r '.mcp.cq.command[0]' "${TARGET}/opencode.json")
mcp_arg=$(jq -r '.mcp.cq.command[1]' "${TARGET}/opencode.json")
assert_eq "MCP command is python3" "python3" "${mcp_cmd}"
assert_eq "MCP arg is bootstrap.py" "${BOOTSTRAP}" "${mcp_arg}"

# AGENTS.md.
assert_exists "AGENTS.md exists" "${TARGET}/AGENTS.md"
assert_contains "AGENTS.md has cq marker" "<!-- cq:start -->" "$(cat "${TARGET}/AGENTS.md")"

# ── Idempotent re-install ────────────────────────────────────────────

echo ""
echo "=== Test: idempotent re-install ==="

output=$(bash "${INSTALL}" install --project "${PROJECT}" 2>&1)
assert_contains "MCP says already configured" "already configured" "${output}"
assert_contains "AGENTS.md says already present" "already present" "${output}"

# Config unchanged.
mcp_cmd=$(jq -r '.mcp.cq.command[0]' "${TARGET}/opencode.json")
assert_eq "MCP command still python3" "python3" "${mcp_cmd}"

# ── Stale MCP config gets updated ────────────────────────────────────

echo ""
echo "=== Test: stale MCP config updated ==="

PROJECT_STALE="${TMPDIR_ROOT}/stale"
TARGET_STALE="${PROJECT_STALE}/.opencode"
mkdir -p "${TARGET_STALE}"

# Write an old-style config that uses uv instead of bootstrap.py.
cat > "${TARGET_STALE}/opencode.json" <<'EOF'
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "cq": {
      "environment": { "CQ_TEAM_ADDR": "http://localhost:8742" },
      "type": "local",
      "command": ["uv", "run", "--directory", "/old/path/server", "cq-mcp-server"]
    }
  }
}
EOF

output=$(bash "${INSTALL}" install --project "${PROJECT_STALE}" 2>&1)
assert_contains "MCP says updated" "Updated CQ MCP server" "${output}"

mcp_cmd=$(jq -r '.mcp.cq.command[0]' "${TARGET_STALE}/opencode.json")
mcp_arg=$(jq -r '.mcp.cq.command[1]' "${TARGET_STALE}/opencode.json")
assert_eq "stale MCP command updated to python3" "python3" "${mcp_cmd}"
assert_eq "stale MCP arg updated to bootstrap.py" "${BOOTSTRAP}" "${mcp_arg}"

# Old environment key should be removed.
has_env=$(jq 'has("environment") // (.mcp.cq | has("environment"))' "${TARGET_STALE}/opencode.json")
assert_eq "stale environment removed" "false" "${has_env}"

# ── Existing config with other MCP servers preserved ─────────────────

echo ""
echo "=== Test: other MCP servers preserved ==="

PROJECT_OTHER="${TMPDIR_ROOT}/other"
TARGET_OTHER="${PROJECT_OTHER}/.opencode"
mkdir -p "${TARGET_OTHER}"

cat > "${TARGET_OTHER}/opencode.json" <<'EOF'
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "other-tool": { "type": "local", "command": ["other-cmd"] }
  }
}
EOF

bash "${INSTALL}" install --project "${PROJECT_OTHER}" >/dev/null

other_cmd=$(jq -r '.mcp["other-tool"].command[0]' "${TARGET_OTHER}/opencode.json")
assert_eq "other MCP server preserved" "other-cmd" "${other_cmd}"
mcp_cmd=$(jq -r '.mcp.cq.command[0]' "${TARGET_OTHER}/opencode.json")
assert_eq "cq MCP server added alongside" "python3" "${mcp_cmd}"

# ── Uninstall ────────────────────────────────────────────────────────

echo ""
echo "=== Test: uninstall ==="

bash "${INSTALL}" uninstall --project "${PROJECT}" >/dev/null

assert_not_exists "skill removed" "${TARGET}/skills/cq"
assert_not_exists "cq-reflect removed" "${TARGET}/commands/cq-reflect.md"
assert_not_exists "cq-status removed" "${TARGET}/commands/cq-status.md"
assert_not_exists "AGENTS.md removed" "${TARGET}/AGENTS.md"

# opencode.json should still exist but without .mcp.cq.
has_cq=$(jq 'has("mcp") and (.mcp | has("cq"))' "${TARGET}/opencode.json" 2>/dev/null || echo "false")
assert_eq "MCP cq entry removed" "false" "${has_cq}"

# ── Uninstall preserves other MCP servers ────────────────────────────

echo ""
echo "=== Test: uninstall preserves other MCP servers ==="

bash "${INSTALL}" uninstall --project "${PROJECT_OTHER}" >/dev/null

other_cmd=$(jq -r '.mcp["other-tool"].command[0]' "${TARGET_OTHER}/opencode.json")
assert_eq "other MCP server still present" "other-cmd" "${other_cmd}"
has_cq=$(jq '.mcp | has("cq")' "${TARGET_OTHER}/opencode.json")
assert_eq "cq removed from config" "false" "${has_cq}"

# ── AGENTS.md with other content preserved ───────────────────────────

echo ""
echo "=== Test: AGENTS.md other content preserved ==="

PROJECT_AGENTS="${TMPDIR_ROOT}/agents"
TARGET_AGENTS="${PROJECT_AGENTS}/.opencode"
mkdir -p "${TARGET_AGENTS}"

cat > "${TARGET_AGENTS}/AGENTS.md" <<'EOF'
# My Custom Rules

Do something important.
EOF

bash "${INSTALL}" install --project "${PROJECT_AGENTS}" >/dev/null
assert_contains "custom content preserved after install" "Do something important" "$(cat "${TARGET_AGENTS}/AGENTS.md")"
assert_contains "cq section added" "<!-- cq:start -->" "$(cat "${TARGET_AGENTS}/AGENTS.md")"

bash "${INSTALL}" uninstall --project "${PROJECT_AGENTS}" >/dev/null
assert_contains "custom content preserved after uninstall" "Do something important" "$(cat "${TARGET_AGENTS}/AGENTS.md")"

if grep -q "cq:start" "${TARGET_AGENTS}/AGENTS.md"; then
    echo "  FAIL: cq markers should be removed after uninstall"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: cq markers removed after uninstall"
    PASS=$((PASS + 1))
fi

# ── Double uninstall is safe ─────────────────────────────────────────

echo ""
echo "=== Test: double uninstall ==="

output=$(bash "${INSTALL}" uninstall --project "${PROJECT}" 2>&1)
# Should not error.
assert_eq "double uninstall exits 0" "0" "$?"

# ── Summary ──────────────────────────────────────────────────────────

echo ""
echo "==============================="
echo "  ${PASS} passed, ${FAIL} failed"
echo "==============================="

[[ "${FAIL}" -eq 0 ]]
