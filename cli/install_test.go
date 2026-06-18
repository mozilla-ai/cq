package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func runInstall(t *testing.T, args ...string) (string, error) {
	t.Helper()
	root := newRootCmd()
	var out bytes.Buffer
	root.SetOut(&out)
	root.SetErr(&out)
	root.SetArgs(append([]string{"install"}, args...))
	err := root.Execute()
	return out.String(), err
}

// setTestHome sets both HOME (Unix) and USERPROFILE (Windows) so
// os.UserHomeDir() resolves to the temp dir on all platforms.
func setTestHome(t *testing.T, home string) {
	t.Helper()
	t.Setenv("HOME", home)
	t.Setenv("USERPROFILE", home)
}

func TestInstallRequiresAHost(t *testing.T) {
	_, err := runInstall(t)
	require.Error(t, err)
	require.Contains(t, err.Error(), "select at least one --target")
}

func TestInstallCodexEndToEnd(t *testing.T) {
	home := t.TempDir()
	setTestHome(t, home)
	bin := filepath.Join(t.TempDir(), "cq")
	t.Setenv("CQ_INSTALL_BINARY", bin)

	out, err := runInstall(t, "--target", "codex")
	require.NoError(t, err)
	require.Contains(t, out, "[codex]")

	require.FileExists(t, filepath.Join(home, ".agents", "skills", "cq", "SKILL.md"))
	require.FileExists(t, filepath.Join(home, ".codex", "config.toml"))
	require.FileExists(t, filepath.Join(home, ".codex", "AGENTS.md"))

	// Config contains the MCP server entry.
	config, err := os.ReadFile(filepath.Join(home, ".codex", "config.toml"))
	require.NoError(t, err)
	require.Contains(t, string(config), "[mcp_servers.cq]")
	require.Contains(t, string(config), bin)

	// Re-run is idempotent.
	_, err = runInstall(t, "--target", "codex")
	require.NoError(t, err)

	// Uninstall reverses MCP and AGENTS.md but keeps shared skill.
	_, err = runInstall(t, "--target", "codex", "--uninstall")
	require.NoError(t, err)
	configAfter, err := os.ReadFile(filepath.Join(home, ".codex", "config.toml"))
	require.NoError(t, err)
	require.NotContains(t, string(configAfter), "mcp_servers")
	require.NoFileExists(t, filepath.Join(home, ".codex", "AGENTS.md"))
	require.FileExists(t, filepath.Join(home, ".agents", "skills", "cq", "SKILL.md"))
}

func TestInstallCopilotEndToEnd(t *testing.T) {
	home := t.TempDir()
	setTestHome(t, home)
	bin := filepath.Join(t.TempDir(), "cq")
	t.Setenv("CQ_INSTALL_BINARY", bin)

	out, err := runInstall(t, "--target", "copilot")
	require.NoError(t, err)
	require.Contains(t, out, "[copilot]")

	require.FileExists(t, filepath.Join(home, ".agents", "skills", "cq", "SKILL.md"))
	require.FileExists(t, filepath.Join(home, ".copilot", "instructions", "cq.md"))

	// Re-run is idempotent.
	_, err = runInstall(t, "--target", "copilot")
	require.NoError(t, err)

	// Uninstall reverses instruction but keeps shared skill.
	_, err = runInstall(t, "--target", "copilot", "--uninstall")
	require.NoError(t, err)
	require.NoFileExists(t, filepath.Join(home, ".copilot", "instructions", "cq.md"))
	require.FileExists(t, filepath.Join(home, ".agents", "skills", "cq", "SKILL.md"))
}

func TestInstallClaudeDryRun(t *testing.T) {
	home := t.TempDir()
	setTestHome(t, home)
	bin := filepath.Join(t.TempDir(), "cq")
	t.Setenv("CQ_INSTALL_BINARY", bin)

	out, err := runInstall(t, "--target", "claude", "--dry-run")
	require.NoError(t, err)
	require.Contains(t, out, "[claude]")
	require.Contains(t, out, "claude marketplace")
}

func TestInstallCursorEndToEnd(t *testing.T) {
	home := t.TempDir()
	setTestHome(t, home)
	bin := filepath.Join(t.TempDir(), "cq")
	t.Setenv("CQ_INSTALL_BINARY", bin)

	out, err := runInstall(t, "--target", "cursor")
	require.NoError(t, err)
	require.Contains(t, out, "[cursor]")

	require.FileExists(t, filepath.Join(home, ".agents", "skills", "cq", "SKILL.md"))
	require.FileExists(t, filepath.Join(home, ".cursor", "mcp.json"))
	require.FileExists(t, filepath.Join(home, ".cursor", "hooks.json"))
	require.FileExists(t, filepath.Join(home, ".cursor", "rules", "cq.mdc"))

	_, err = runInstall(t, "--target", "cursor", "--uninstall")
	require.NoError(t, err)
	require.NoFileExists(t, filepath.Join(home, ".cursor", "rules", "cq.mdc"))
	// Shared skill survives uninstall.
	require.FileExists(t, filepath.Join(home, ".agents", "skills", "cq", "SKILL.md"))
}

func TestInstallPiEndToEnd(t *testing.T) {
	home := t.TempDir()
	setTestHome(t, home)
	bin := filepath.Join(t.TempDir(), "cq")
	t.Setenv("CQ_INSTALL_BINARY", bin)

	out, err := runInstall(t, "--target", "pi")
	require.NoError(t, err)
	require.Contains(t, out, "[pi]")

	require.FileExists(t, filepath.Join(home, ".agents", "skills", "cq", "SKILL.md"))
	require.FileExists(t, filepath.Join(home, ".pi", "agent", "prompts", "cq-reflect.md"))
	require.FileExists(t, filepath.Join(home, ".pi", "agent", "prompts", "cq-status.md"))
	require.FileExists(t, filepath.Join(home, ".pi", "agent", "AGENTS.md"))

	// AGENTS.md embeds the binary path in CLI mappings.
	agents, err := os.ReadFile(filepath.Join(home, ".pi", "agent", "AGENTS.md"))
	require.NoError(t, err)
	require.Contains(t, string(agents), bin)
	require.Contains(t, string(agents), bin+" query")

	// Re-run is idempotent.
	_, err = runInstall(t, "--target", "pi")
	require.NoError(t, err)

	// Uninstall reverses prompts and AGENTS.md but keeps shared skill.
	_, err = runInstall(t, "--target", "pi", "--uninstall")
	require.NoError(t, err)
	require.NoDirExists(t, filepath.Join(home, ".pi", "agent", "prompts"))
	require.NoFileExists(t, filepath.Join(home, ".pi", "agent", "AGENTS.md"))
	require.FileExists(t, filepath.Join(home, ".agents", "skills", "cq", "SKILL.md"))
}

func TestInstallOpencodeEndToEnd(t *testing.T) {
	home := t.TempDir()
	setTestHome(t, home)
	t.Setenv("OPENCODE_CONFIG_DIR", "")
	bin := filepath.Join(t.TempDir(), "cq")
	t.Setenv("CQ_INSTALL_BINARY", bin)

	out, err := runInstall(t, "--target", "opencode")
	require.NoError(t, err)
	require.Contains(t, out, "[opencode]")

	require.FileExists(t, filepath.Join(home, ".agents", "skills", "cq", "SKILL.md"))
	require.FileExists(t, filepath.Join(home, ".config", "opencode", "opencode.json"))
	require.FileExists(t, filepath.Join(home, ".config", "opencode", "commands", "reflect.md"))
	require.FileExists(t, filepath.Join(home, ".config", "opencode", "commands", "status.md"))
	require.FileExists(t, filepath.Join(home, ".config", "opencode", "AGENTS.md"))

	cfg := filepath.Join(home, ".config", "opencode", "opencode.json")
	data, err := os.ReadFile(cfg)
	require.NoError(t, err)
	var m map[string]any
	require.NoError(t, json.Unmarshal(data, &m))
	mcp := m["mcp"].(map[string]any)
	cq := mcp["cq"].(map[string]any)
	require.Equal(t, "local", cq["type"])
	cmd := cq["command"].([]any)
	require.Equal(t, bin, cmd[0])
	require.Equal(t, "mcp", cmd[1])

	// Re-run is idempotent.
	_, err = runInstall(t, "--target", "opencode")
	require.NoError(t, err)

	// Uninstall reverses config and commands but keeps shared skill.
	_, err = runInstall(t, "--target", "opencode", "--uninstall")
	require.NoError(t, err)
	data, err = os.ReadFile(cfg)
	require.NoError(t, err)
	m = nil
	require.NoError(t, json.Unmarshal(data, &m))
	require.NotContains(t, m, "mcp")
	require.NoDirExists(t, filepath.Join(home, ".config", "opencode", "commands"))
	require.NoFileExists(t, filepath.Join(home, ".config", "opencode", "AGENTS.md"))
	require.FileExists(t, filepath.Join(home, ".agents", "skills", "cq", "SKILL.md"))
}

func TestInstallWindsurfEndToEnd(t *testing.T) {
	home := t.TempDir()
	setTestHome(t, home)
	bin := filepath.Join(t.TempDir(), "cq")
	t.Setenv("CQ_INSTALL_BINARY", bin)

	_, err := runInstall(t, "--target", "windsurf")
	require.NoError(t, err)

	require.FileExists(t, filepath.Join(home, ".agents", "skills", "cq", "SKILL.md"))
	cfg := filepath.Join(home, ".codeium", "windsurf", "mcp_config.json")
	data, err := os.ReadFile(cfg)
	require.NoError(t, err)
	var m map[string]any
	require.NoError(t, json.Unmarshal(data, &m))
	require.Equal(t, bin,
		m["mcpServers"].(map[string]any)["cq"].(map[string]any)["command"])

	// Re-run is idempotent.
	_, err = runInstall(t, "--target", "windsurf")
	require.NoError(t, err)

	// Uninstall reverses the MCP entry.
	_, err = runInstall(t, "--target", "windsurf", "--uninstall")
	require.NoError(t, err)
	data, err = os.ReadFile(cfg)
	require.NoError(t, err)
	m = nil
	require.NoError(t, json.Unmarshal(data, &m))
	require.NotContains(t, m, "mcpServers")
}
