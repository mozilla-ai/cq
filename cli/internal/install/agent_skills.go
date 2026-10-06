package install

import (
	"os"
	"path/filepath"
	"strings"

	"github.com/mozilla-ai/cq/sdk/go/prompts"
)

// agentSkillsHost installs the shared cq skill and a portable reflection skill.
// Tool configuration and slash commands are outside the Agent Skills format.
type agentSkillsHost struct{}

func (agentSkillsHost) GlobalTarget(home string) string { return SharedSkillsDir(home) }

func (agentSkillsHost) Install(ctx Context) ([]Change, error) {
	shared, err := writeManagedFiles(ctx.SkillsDir, map[string]string{
		filepath.Join("cq", "SKILL.md"): prompts.Skill(),
	}, ctx.DryRun)
	if err != nil {
		return nil, err
	}

	// Keep a separate manifest: other hosts rewrite the shared root manifest
	// with only cq/SKILL.md and would otherwise prune cq-reflect on reinstall.
	reflection, err := writeManagedFiles(filepath.Join(ctx.Target, "cq-reflect"), map[string]string{
		"SKILL.md": reflectSkill(),
	}, ctx.DryRun)
	if err != nil {
		return nil, err
	}
	return []Change{shared, reflection}, nil
}

func (agentSkillsHost) Name() Target { return TargetAgentSkills }

func (agentSkillsHost) SupportsProject() bool { return false }

// Uninstall removes only the reflection skill; the shared cq skill may still
// be used by another host.
func (agentSkillsHost) Uninstall(ctx Context) ([]Change, error) {
	dir := filepath.Join(ctx.Target, "cq-reflect")
	change, err := removeManagedFiles(dir, ctx.DryRun)
	if err != nil {
		return nil, err
	}
	if change.Action == ActionRemoved && !ctx.DryRun {
		_ = os.Remove(dir) // Best-effort: keep user files if the directory is not empty.
	}
	return []Change{change}, nil
}

// reflectSkill adapts the canonical command prompt to a skill without
// advertising host-specific slash-command syntax.
func reflectSkill() string {
	body := strings.Replace(prompts.Reflect(), "name: cq:reflect\n", "name: cq-reflect\n", 1)
	body = strings.Replace(body, "# /cq:reflect", "# cq-reflect\n\nLoad the `cq` skill before reflecting; it defines the VIBE√ safety check and cq tool protocol.", 1)
	return strings.ReplaceAll(body, "/cq:reflect", "cq-reflect")
}
