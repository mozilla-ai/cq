package install

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/mozilla-ai/cq/sdk/go/prompts"
)

func cursorCtx(t *testing.T) Context {
	t.Helper()
	root := t.TempDir()
	return Context{
		Target:     filepath.Join(root, ".cursor"),
		SkillsDir:  SharedSkillsDir(root),
		BinaryPath: filepath.Join(root, "bin", "cq"),
	}
}

func TestCursorInstallWritesAllAssets(t *testing.T) {
	ctx := cursorCtx(t)
	changes, err := cursorHost{}.Install(ctx)
	require.NoError(t, err)
	require.NotEmpty(t, changes)

	// Shared skill.
	skill, err := os.ReadFile(filepath.Join(ctx.SkillsDir, "cq", "SKILL.md"))
	require.NoError(t, err)
	require.Equal(t, prompts.Skill(), string(skill))

	// MCP entry references the binary and the mcp subcommand.
	mcp := readJSON(t, filepath.Join(ctx.Target, "mcp.json"))
	cq := mcp["mcpServers"].(map[string]any)["cq"].(map[string]any)
	require.Equal(t, ctx.BinaryPath, cq["command"])
	require.Equal(t, []any{"mcp"}, cq["args"])

	// Rule.
	rule, err := os.ReadFile(filepath.Join(ctx.Target, "rules", "cq.mdc"))
	require.NoError(t, err)
	require.Contains(t, string(rule), "alwaysApply: true")

	// Four hook entries, each pointing at the binary's _hook with the state dir.
	hooks := readJSON(t, filepath.Join(ctx.Target, "hooks.json"))["hooks"].(map[string]any)
	for _, key := range []string{"sessionStart", "postToolUseFailure", "postToolUse", "stop"} {
		entries := hooks[key].([]any)
		require.Len(t, entries, 1)
		cmd := entries[0].(map[string]any)["command"].(string)
		require.Contains(t, cmd, "_hook")
		require.Contains(t, cmd, "--host cursor")
		require.Contains(t, cmd, filepath.Join(ctx.Target, "cq-hook-state"))
	}
}

func TestCursorInstallIsIdempotent(t *testing.T) {
	ctx := cursorCtx(t)
	_, err := cursorHost{}.Install(ctx)
	require.NoError(t, err)
	changes, err := cursorHost{}.Install(ctx)
	require.NoError(t, err)
	for _, c := range changes {
		require.NotEqual(t, ActionCreated, c.Action)
	}
}

func TestCursorUninstallReversesButKeepsSharedSkill(t *testing.T) {
	ctx := cursorCtx(t)
	_, err := cursorHost{}.Install(ctx)
	require.NoError(t, err)

	_, err = cursorHost{}.Uninstall(ctx)
	require.NoError(t, err)

	// MCP entry gone.
	mcp := readJSON(t, filepath.Join(ctx.Target, "mcp.json"))
	require.NotContains(t, mcp, "mcpServers")
	// Rule gone.
	require.NoFileExists(t, filepath.Join(ctx.Target, "rules", "cq.mdc"))
	// Hook entries gone.
	hooks := readJSON(t, filepath.Join(ctx.Target, "hooks.json"))["hooks"].(map[string]any)
	require.Empty(t, hooks)
	// State dir gone.
	require.NoDirExists(t, filepath.Join(ctx.Target, "cq-hook-state"))
	// Shared skill REMAINS (it is the cross-host commons).
	require.FileExists(t, filepath.Join(ctx.SkillsDir, "cq", "SKILL.md"))
}

func TestCursorUninstallLeavesUserModifiedRule(t *testing.T) {
	ctx := cursorCtx(t)
	_, err := cursorHost{}.Install(ctx)
	require.NoError(t, err)
	rulePath := filepath.Join(ctx.Target, "rules", "cq.mdc")
	require.NoError(t, os.WriteFile(rulePath, []byte("user edited\n"), 0o644))

	_, err = cursorHost{}.Uninstall(ctx)
	require.NoError(t, err)
	require.FileExists(t, rulePath)
}

func TestCursorRegisteredAndProject(t *testing.T) {
	h, ok := hosts[TargetCursor]
	require.True(t, ok)
	require.Equal(t, TargetCursor, h.Name())
	require.False(t, h.SupportsProject())
}
