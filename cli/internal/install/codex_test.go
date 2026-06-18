package install

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/mozilla-ai/cq/sdk/go/prompts"
)

func codexCtx(t *testing.T) Context {
	t.Helper()
	root := t.TempDir()
	return Context{
		BinaryPath: filepath.Join(root, "bin", "cq"),
		Home:       root,
		SkillsDir:  SharedSkillsDir(root),
		Target:     filepath.Join(root, ".codex"),
	}
}

func TestCodexInstallWritesAllAssets(t *testing.T) {
	ctx := codexCtx(t)
	changes, err := codexHost{}.Install(ctx)
	require.NoError(t, err)
	require.NotEmpty(t, changes)

	// Shared skill.
	skill, err := os.ReadFile(filepath.Join(ctx.SkillsDir, "cq", "SKILL.md"))
	require.NoError(t, err)
	require.Equal(t, prompts.Skill(), string(skill))

	// MCP entry in TOML config.
	config, err := os.ReadFile(filepath.Join(ctx.Target, "config.toml"))
	require.NoError(t, err)
	require.Contains(t, string(config), "[mcp_servers.cq]")
	require.Contains(t, string(config), ctx.BinaryPath)

	// AGENTS.md block.
	agents, err := os.ReadFile(filepath.Join(ctx.Target, "AGENTS.md"))
	require.NoError(t, err)
	require.Contains(t, string(agents), cqBlock.start)
	require.Contains(t, string(agents), cqBlock.end)
	require.Contains(t, string(agents), "Core Protocol")
}

func TestCodexInstallIsIdempotent(t *testing.T) {
	ctx := codexCtx(t)
	_, err := codexHost{}.Install(ctx)
	require.NoError(t, err)
	changes, err := codexHost{}.Install(ctx)
	require.NoError(t, err)
	for _, c := range changes {
		require.NotEqual(t, ActionCreated, c.Action)
	}
}

func TestCodexUninstallReversesButKeepsSharedSkill(t *testing.T) {
	ctx := codexCtx(t)
	_, err := codexHost{}.Install(ctx)
	require.NoError(t, err)
	_, err = codexHost{}.Uninstall(ctx)
	require.NoError(t, err)

	// MCP entry gone.
	config, err := os.ReadFile(filepath.Join(ctx.Target, "config.toml"))
	require.NoError(t, err)
	require.NotContains(t, string(config), "mcp_servers")
	// AGENTS.md gone (file deleted when only our block).
	require.NoFileExists(t, filepath.Join(ctx.Target, "AGENTS.md"))
	// Shared skill REMAINS.
	require.FileExists(t, filepath.Join(ctx.SkillsDir, "cq", "SKILL.md"))
}

func TestCodexRegisteredAndProject(t *testing.T) {
	h, ok := hosts[TargetCodex]
	require.True(t, ok)
	require.Equal(t, TargetCodex, h.Name())
	require.False(t, h.SupportsProject())
}

func TestCodexTargetPath(t *testing.T) {
	require.Equal(t, filepath.Join("/home/dev", ".codex"), codexTarget("/home/dev"))
}
