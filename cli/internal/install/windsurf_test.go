package install

import (
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestWindsurfInstallWritesSkillAndMCP(t *testing.T) {
	home := t.TempDir()
	h := windsurfHost{}
	ctx := Context{
		Target:     h.GlobalTarget(home),
		SkillsDir:  SharedSkillsDir(home),
		BinaryPath: "/opt/homebrew/bin/cq",
	}
	changes, err := h.Install(ctx)
	require.NoError(t, err)
	require.NotEmpty(t, changes)

	require.FileExists(t, filepath.Join(home, ".agents", "skills", "cq", "SKILL.md"))
	cfg := filepath.Join(home, ".codeium", "windsurf", "mcp_config.json")
	require.FileExists(t, cfg)
	m := readJSON(t, cfg)
	servers := m["mcpServers"].(map[string]any)
	cq := servers["cq"].(map[string]any)
	require.Equal(t, "/opt/homebrew/bin/cq", cq["command"])
	require.Equal(t, []any{"mcp"}, cq["args"])
}

func TestWindsurfUninstallReverses(t *testing.T) {
	home := t.TempDir()
	h := windsurfHost{}
	ctx := Context{Target: h.GlobalTarget(home), SkillsDir: SharedSkillsDir(home), BinaryPath: "/opt/homebrew/bin/cq"}
	_, err := h.Install(ctx)
	require.NoError(t, err)
	_, err = h.Uninstall(ctx)
	require.NoError(t, err)

	m := readJSON(t, filepath.Join(home, ".codeium", "windsurf", "mcp_config.json"))
	require.NotContains(t, m, "mcpServers")
}

func TestWindsurfRegistered(t *testing.T) {
	hosts := SelectHosts(Selection{Windsurf: true})
	require.Len(t, hosts, 1)
	require.Equal(t, "windsurf", hosts[0].Name())
}

func TestWindsurfUninstallLeavesSharedSkill(t *testing.T) {
	home := t.TempDir()
	h := windsurfHost{}
	ctx := Context{Target: h.GlobalTarget(home), SkillsDir: SharedSkillsDir(home), BinaryPath: "/opt/homebrew/bin/cq"}
	_, err := h.Install(ctx)
	require.NoError(t, err)
	_, err = h.Uninstall(ctx)
	require.NoError(t, err)
	require.FileExists(t, filepath.Join(home, ".agents", "skills", "cq", "SKILL.md"))
}
