package install

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/mozilla-ai/cq/sdk/go/prompts"
)

func copilotCtx(t *testing.T) Context {
	t.Helper()
	root := t.TempDir()
	return Context{
		Home:       root,
		Target:     copilotTarget(root),
		SkillsDir:  SharedSkillsDir(root),
		BinaryPath: filepath.Join(root, "bin", "cq"),
	}
}

func TestCopilotInstallWritesAllAssets(t *testing.T) {
	ctx := copilotCtx(t)
	changes, err := copilotHost{}.Install(ctx)
	require.NoError(t, err)
	require.NotEmpty(t, changes)

	// Shared skill.
	skill, err := os.ReadFile(filepath.Join(ctx.SkillsDir, "cq", "SKILL.md"))
	require.NoError(t, err)
	require.Equal(t, prompts.Skill(), string(skill))

	// MCP entry uses servers key, type:stdio, and array args.
	config := readJSON(t, filepath.Join(ctx.Target, "mcp.json"))
	servers := config["servers"].(map[string]any)
	cq := servers["cq"].(map[string]any)
	require.Equal(t, "stdio", cq["type"])
	require.Equal(t, ctx.BinaryPath, cq["command"])
	require.Equal(t, []any{"mcp"}, cq["args"])

	// Global instruction file matches the managed content exactly.
	instruction, err := os.ReadFile(filepath.Join(ctx.Home, ".copilot", "instructions", "cq.md"))
	require.NoError(t, err)
	require.Equal(t, copilotInstruction, string(instruction))
}

func TestCopilotInstallIsIdempotent(t *testing.T) {
	ctx := copilotCtx(t)
	_, err := copilotHost{}.Install(ctx)
	require.NoError(t, err)
	changes, err := copilotHost{}.Install(ctx)
	require.NoError(t, err)
	for _, c := range changes {
		require.NotEqual(t, ActionCreated, c.Action)
	}
}

func TestCopilotUninstallReversesButKeepsSharedSkill(t *testing.T) {
	ctx := copilotCtx(t)
	_, err := copilotHost{}.Install(ctx)
	require.NoError(t, err)
	_, err = copilotHost{}.Uninstall(ctx)
	require.NoError(t, err)

	// MCP entry gone.
	config := readJSON(t, filepath.Join(ctx.Target, "mcp.json"))
	require.NotContains(t, config, "servers")
	// Instruction file gone.
	require.NoFileExists(t, filepath.Join(ctx.Home, ".copilot", "instructions", "cq.md"))
	// Shared skill REMAINS (it is the cross-host commons).
	require.FileExists(t, filepath.Join(ctx.SkillsDir, "cq", "SKILL.md"))
}

func TestCopilotUninstallLeavesUserModifiedInstruction(t *testing.T) {
	ctx := copilotCtx(t)
	_, err := copilotHost{}.Install(ctx)
	require.NoError(t, err)
	instructionPath := filepath.Join(ctx.Home, ".copilot", "instructions", "cq.md")
	require.NoError(t, os.WriteFile(instructionPath, []byte("user edited\n"), 0o644))

	_, err = copilotHost{}.Uninstall(ctx)
	require.NoError(t, err)
	require.FileExists(t, instructionPath)
}

func TestCopilotRegisteredAndProject(t *testing.T) {
	h, ok := hosts[TargetCopilot]
	require.True(t, ok)
	require.Equal(t, TargetCopilot, h.Name())
	require.False(t, h.SupportsProject())
}

func TestCopilotTargetPath(t *testing.T) {
	home := "/home/dev"
	got := copilotTarget(home)
	switch runtime.GOOS {
	case "darwin":
		require.Equal(t, filepath.Join(home, "Library", "Application Support", "Code", "User"), got)
	case "windows":
		require.Equal(t, filepath.Join(home, "AppData", "Roaming", "Code", "User"), got)
	default:
		require.Equal(t, filepath.Join(home, ".config", "Code", "User"), got)
	}
}
