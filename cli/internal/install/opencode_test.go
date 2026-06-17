package install

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/mozilla-ai/cq/sdk/go/prompts"
)

func opencodeCtx(t *testing.T) Context {
	t.Helper()
	root := t.TempDir()
	return Context{
		Target:     filepath.Join(root, ".config", "opencode"),
		SkillsDir:  SharedSkillsDir(root),
		BinaryPath: filepath.Join(root, "bin", "cq"),
	}
}

func TestOpencodeInstallWritesAllAssets(t *testing.T) {
	ctx := opencodeCtx(t)
	changes, err := opencodeHost{}.Install(ctx)
	require.NoError(t, err)
	require.NotEmpty(t, changes)

	// Shared skill.
	skill, err := os.ReadFile(filepath.Join(ctx.SkillsDir, "cq", "SKILL.md"))
	require.NoError(t, err)
	require.Equal(t, prompts.Skill(), string(skill))

	// MCP entry uses array command and local type.
	config := readJSON(t, filepath.Join(ctx.Target, "opencode.json"))
	require.Equal(t, opencodeSchemaURL, config["$schema"])
	mcp := config["mcp"].(map[string]any)
	cq := mcp["cq"].(map[string]any)
	require.Equal(t, "local", cq["type"])
	cmd := cq["command"].([]any)
	require.Equal(t, ctx.BinaryPath, cmd[0])
	require.Equal(t, "mcp", cmd[1])

	// Command files are transformed (name: stripped, agent: build added).
	for _, name := range []string{"reflect.md", "status.md"} {
		got, err := os.ReadFile(filepath.Join(ctx.Target, "commands", name))
		require.NoError(t, err)
		require.Contains(t, string(got), "agent: build")
		require.NotContains(t, string(got), "name:")
	}

	// AGENTS.md block.
	agents, err := os.ReadFile(filepath.Join(ctx.Target, "AGENTS.md"))
	require.NoError(t, err)
	require.Contains(t, string(agents), cqBlock.start)
	require.Contains(t, string(agents), cqBlock.end)
	require.Contains(t, string(agents), "Core Protocol")
}

func TestOpencodeInstallIsIdempotent(t *testing.T) {
	ctx := opencodeCtx(t)
	_, err := opencodeHost{}.Install(ctx)
	require.NoError(t, err)
	changes, err := opencodeHost{}.Install(ctx)
	require.NoError(t, err)
	for _, c := range changes {
		require.NotEqual(t, ActionCreated, c.Action)
	}
}

func TestOpencodeInstallPreservesSchemaOnReinstall(t *testing.T) {
	ctx := opencodeCtx(t)
	_, err := opencodeHost{}.Install(ctx)
	require.NoError(t, err)
	config := readJSON(t, filepath.Join(ctx.Target, "opencode.json"))
	require.Equal(t, opencodeSchemaURL, config["$schema"])

	_, err = opencodeHost{}.Install(ctx)
	require.NoError(t, err)
	config = readJSON(t, filepath.Join(ctx.Target, "opencode.json"))
	require.Equal(t, opencodeSchemaURL, config["$schema"])
}

func TestOpencodeUninstallReversesButKeepsSharedSkill(t *testing.T) {
	ctx := opencodeCtx(t)
	_, err := opencodeHost{}.Install(ctx)
	require.NoError(t, err)
	_, err = opencodeHost{}.Uninstall(ctx)
	require.NoError(t, err)

	// MCP entry gone.
	config := readJSON(t, filepath.Join(ctx.Target, "opencode.json"))
	require.NotContains(t, config, "mcp")
	// Commands gone (dir pruned).
	require.NoDirExists(t, filepath.Join(ctx.Target, "commands"))
	// AGENTS.md gone (file deleted when only our block).
	require.NoFileExists(t, filepath.Join(ctx.Target, "AGENTS.md"))
	// Shared skill REMAINS (it is the cross-host commons).
	require.FileExists(t, filepath.Join(ctx.SkillsDir, "cq", "SKILL.md"))
}

func TestOpencodeRegisteredAndProject(t *testing.T) {
	h, ok := hosts[TargetOpenCode]
	require.True(t, ok)
	require.Equal(t, TargetOpenCode, h.Name())
	require.False(t, h.SupportsProject())
}

func TestOpencodeTargetHonorsEnvOverride(t *testing.T) {
	t.Setenv(opencodeConfigDirEnv, "/custom/opencode")
	require.Equal(t, "/custom/opencode", opencodeTarget("/home/dev"))
}

func TestOpencodeTargetDefaultPath(t *testing.T) {
	t.Setenv(opencodeConfigDirEnv, "")
	require.Equal(t, filepath.Join("/home/dev", ".config", "opencode"), opencodeTarget("/home/dev"))
}
