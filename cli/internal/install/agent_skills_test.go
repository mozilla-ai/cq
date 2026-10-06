package install

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func agentSkillsCtx(t *testing.T) Context {
	t.Helper()
	home := t.TempDir()
	host := agentSkillsHost{}
	return Context{Home: home, Target: host.GlobalTarget(home), SkillsDir: SharedSkillsDir(home)}
}

func TestAgentSkillsInstallWritesPortableCQSkills(t *testing.T) {
	ctx := agentSkillsCtx(t)
	changes, err := agentSkillsHost{}.Install(ctx)
	require.NoError(t, err)
	require.Len(t, changes, 2)

	shared, err := os.ReadFile(filepath.Join(ctx.SkillsDir, "cq", "SKILL.md"))
	require.NoError(t, err)
	require.Contains(t, string(shared), "name: cq")

	reflectionPath := filepath.Join(ctx.Target, "cq-reflect", "SKILL.md")
	reflection, err := os.ReadFile(reflectionPath)
	require.NoError(t, err)
	require.Contains(t, string(reflection), "name: cq-reflect")
	require.Contains(t, string(reflection), "# cq-reflect")
	require.Contains(t, string(reflection), "Load the `cq` skill")
	require.NotContains(t, string(reflection), "name: cq:reflect")
	require.NotContains(t, string(reflection), "/cq:reflect")

	// Keep reflection ownership out of the shared manifest used by existing hosts.
	sharedManifest, err := loadManifest(filepath.Join(ctx.SkillsDir, manifestName))
	require.NoError(t, err)
	require.Len(t, sharedManifest.Files, 1)
	require.Equal(t, filepath.Join("cq", "SKILL.md"), sharedManifest.Files[0].Path)
	reflectionManifest, err := loadManifest(filepath.Join(ctx.Target, "cq-reflect", manifestName))
	require.NoError(t, err)
	require.Len(t, reflectionManifest.Files, 1)
	require.Equal(t, "SKILL.md", reflectionManifest.Files[0].Path)
}

func TestAgentSkillsReinstallIsIdempotent(t *testing.T) {
	ctx := agentSkillsCtx(t)
	host := agentSkillsHost{}
	_, err := host.Install(ctx)
	require.NoError(t, err)
	changes, err := host.Install(ctx)
	require.NoError(t, err)
	for _, change := range changes {
		require.Equal(t, ActionUnchanged, change.Action)
	}
}

func TestAgentSkillsUninstallKeepsSharedSkillAndUserChanges(t *testing.T) {
	ctx := agentSkillsCtx(t)
	host := agentSkillsHost{}
	_, err := host.Install(ctx)
	require.NoError(t, err)
	reflectionPath := filepath.Join(ctx.Target, "cq-reflect", "SKILL.md")
	require.NoError(t, os.WriteFile(reflectionPath, []byte("user edit"), 0o644))

	changes, err := host.Uninstall(ctx)
	require.NoError(t, err)
	require.Equal(t, ActionSkipped, changes[0].Action)
	body, err := os.ReadFile(reflectionPath)
	require.NoError(t, err)
	require.Equal(t, "user edit", string(body))
	require.FileExists(t, filepath.Join(ctx.SkillsDir, "cq", "SKILL.md"))
}

func TestAgentSkillsUninstallRemovesManagedReflectionOnly(t *testing.T) {
	ctx := agentSkillsCtx(t)
	host := agentSkillsHost{}
	_, err := host.Install(ctx)
	require.NoError(t, err)
	changes, err := host.Uninstall(ctx)
	require.NoError(t, err)
	require.Equal(t, ActionRemoved, changes[0].Action)
	require.NoDirExists(t, filepath.Join(ctx.Target, "cq-reflect"))
	require.FileExists(t, filepath.Join(ctx.SkillsDir, "cq", "SKILL.md"))
}

func TestOtherHostReinstallPreservesReflectionSkill(t *testing.T) {
	ctx := opencodeCtx(t)
	agentCtx := ctx
	agentCtx.Target = ctx.SkillsDir
	_, err := agentSkillsHost{}.Install(agentCtx)
	require.NoError(t, err)
	_, err = opencodeHost{}.Install(ctx)
	require.NoError(t, err)
	_, err = opencodeHost{}.Install(ctx)
	require.NoError(t, err)
	require.FileExists(t, filepath.Join(ctx.SkillsDir, "cq-reflect", "SKILL.md"))
}

func TestAgentSkillsTargetRegistered(t *testing.T) {
	hosts := SelectHosts(Targets{TargetAgentSkills})
	require.Len(t, hosts, 1)
	require.Equal(t, TargetAgentSkills, hosts[0].Name())
	require.False(t, hosts[0].SupportsProject())
}
