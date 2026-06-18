package install

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/mozilla-ai/cq/sdk/go/prompts"
)

func piCtx(t *testing.T) Context {
	t.Helper()
	root := t.TempDir()
	return Context{
		Target:     filepath.Join(root, ".pi", "agent"),
		SkillsDir:  SharedSkillsDir(root),
		BinaryPath: filepath.Join(root, "bin", "cq"),
		CLIVerbs: []CLIVerb{
			{Name: "query", UseLine: "query", FlagUsages: "  --domain\n"},
			{Name: "propose", UseLine: "propose", FlagUsages: "  --summary\n"},
			{Name: "confirm", UseLine: "confirm <unit_id>"},
			{Name: "flag", UseLine: "flag <unit_id>", FlagUsages: "  --reason\n"},
			{Name: "status", UseLine: "status", FlagUsages: "  --format\n"},
		},
	}
}

func TestPiInstallWritesAllAssets(t *testing.T) {
	ctx := piCtx(t)
	changes, err := piHost{}.Install(ctx)
	require.NoError(t, err)
	require.NotEmpty(t, changes)

	// Shared skill.
	skill, err := os.ReadFile(filepath.Join(ctx.SkillsDir, "cq", "SKILL.md"))
	require.NoError(t, err)
	require.Equal(t, prompts.Skill(), string(skill))

	// Prompt files are transformed (name: stripped, /cq: → /cq-).
	for _, name := range []string{"cq-reflect.md", "cq-status.md"} {
		got, err := os.ReadFile(filepath.Join(ctx.Target, "prompts", name))
		require.NoError(t, err)
		require.NotContains(t, string(got), "name:")
		require.NotContains(t, string(got), "/cq:")
	}

	// AGENTS.md block with CLI mappings.
	agents, err := os.ReadFile(filepath.Join(ctx.Target, "AGENTS.md"))
	require.NoError(t, err)
	body := string(agents)
	require.Contains(t, body, cqBlock.start)
	require.Contains(t, body, cqBlock.end)
	require.Contains(t, body, "no cq MCP server")
	require.Contains(t, body, ctx.BinaryPath)
	require.Contains(t, body, "### "+ctx.BinaryPath+" query")
	require.Contains(t, body, "### "+ctx.BinaryPath+" propose")
	require.Contains(t, body, "### "+ctx.BinaryPath+" confirm <unit_id>")
	require.Contains(t, body, "### "+ctx.BinaryPath+" flag <unit_id>")
	require.Contains(t, body, "### "+ctx.BinaryPath+" status")
}

func TestPiInstallIsIdempotent(t *testing.T) {
	ctx := piCtx(t)
	_, err := piHost{}.Install(ctx)
	require.NoError(t, err)
	changes, err := piHost{}.Install(ctx)
	require.NoError(t, err)
	for _, c := range changes {
		require.NotEqual(t, ActionCreated, c.Action)
	}
}

func TestPiUninstallReversesButKeepsSharedSkill(t *testing.T) {
	ctx := piCtx(t)
	_, err := piHost{}.Install(ctx)
	require.NoError(t, err)
	_, err = piHost{}.Uninstall(ctx)
	require.NoError(t, err)

	// Prompts gone (dir pruned).
	require.NoDirExists(t, filepath.Join(ctx.Target, "prompts"))
	// AGENTS.md gone (file deleted when only our block).
	require.NoFileExists(t, filepath.Join(ctx.Target, "AGENTS.md"))
	// Shared skill REMAINS (it is the cross-host commons).
	require.FileExists(t, filepath.Join(ctx.SkillsDir, "cq", "SKILL.md"))
}

func TestPiRegisteredAndProject(t *testing.T) {
	h, ok := hosts[TargetPi]
	require.True(t, ok)
	require.Equal(t, TargetPi, h.Name())
	require.False(t, h.SupportsProject())
}

func TestPiTargetPath(t *testing.T) {
	require.Equal(t, filepath.Join("/home/dev", ".pi", "agent"), piTarget("/home/dev"))
}

func TestTransformPiCommandStripsNameAndRewritesSlash(t *testing.T) {
	source := "---\nname: cq:status\ndescription: Show stats.\n---\n\n# /cq:status\n\nBody.\n"
	got := transformPiCommand(source)
	require.NotContains(t, got, "name:")
	require.Contains(t, got, "description: Show stats.")
	require.Contains(t, got, "# /cq-status")
	require.NotContains(t, got, "/cq:")
}

func TestTransformPiCommandHandlesCRLF(t *testing.T) {
	source := "---\r\nname: cq:reflect\r\ndescription: Mine.\r\n---\r\n\r\n# /cq:reflect\r\n"
	got := transformPiCommand(source)
	require.NotContains(t, got, "name:")
	require.Contains(t, got, "/cq-reflect")
}

func TestTransformPiCommandReturnsUnchangedWithoutFrontmatter(t *testing.T) {
	source := "# No Frontmatter\n"
	require.Equal(t, source, transformPiCommand(source))
}

func TestTransformPiCommandReturnsUnchangedWithUnclosedFrontmatter(t *testing.T) {
	source := "---\nname: broken\n"
	require.Equal(t, source, transformPiCommand(source))
}
