package install

import (
	"path/filepath"

	"github.com/mozilla-ai/cq/sdk/go/prompts"
)

// devinDesktopMCPFile is the MCP configuration file Devin Desktop reads on every platform.
const devinDesktopMCPFile = "mcp_config.json"

// devinDesktopHost installs cq into the Devin Desktop editor (skill commons + MCP entry).
//
// Devin Desktop (formerly Windsurf) stores its config under ~/.codeium/windsurf
// on every platform and is global-only; it reads skills from the shared commons.
type devinDesktopHost struct{}

// GlobalTarget returns the Devin Desktop config dir under home.
func (devinDesktopHost) GlobalTarget(home string) string {
	return devinDesktopTarget(home)
}

// Install writes the shared skill and the cq MCP server entry.
func (devinDesktopHost) Install(ctx Context) ([]Change, error) {
	skill, err := writeManagedFiles(ctx.SkillsDir, map[string]string{
		filepath.Join("cq", "SKILL.md"): prompts.Skill(),
	}, ctx.DryRun)
	if err != nil {
		return nil, err
	}
	mcp, err := upsertJSONEntry(
		filepath.Join(ctx.Target, devinDesktopMCPFile),
		[]string{"mcpServers", "cq"},
		map[string]any{"command": ctx.BinaryPath, "args": []any{"mcp"}},
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}
	return []Change{skill, mcp}, nil
}

// Name returns the host identifier.
func (devinDesktopHost) Name() Target { return TargetDevinDesktop }

// SupportsProject reports that Devin Desktop is global-only.
func (devinDesktopHost) SupportsProject() bool { return false }

// Uninstall removes the cq MCP entry.
//
// NOTE: the skill lives in the shared commons (~/.agents/skills), which other
// hosts may also use, so uninstalling one host must not remove it; the shared
// skill is intentionally left in place.
func (devinDesktopHost) Uninstall(ctx Context) ([]Change, error) {
	mcp, err := removeJSONEntry(
		filepath.Join(ctx.Target, devinDesktopMCPFile),
		[]string{"mcpServers", "cq"},
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}
	return []Change{mcp}, nil
}
