package install

import (
	"path/filepath"

	"github.com/mozilla-ai/cq/sdk/go/prompts"
)

// windsurfMCPFile is the MCP configuration file Windsurf reads on every platform.
const windsurfMCPFile = "mcp_config.json"

// windsurfHost installs cq into the Windsurf editor (skill commons + MCP entry).
//
// Windsurf stores its config under ~/.codeium/windsurf on every platform and
// is global-only; it reads skills from the shared commons.
type windsurfHost struct{}

// init registers the Windsurf adapter so SelectHosts can return it.
func init() {
	registry["windsurf"] = windsurfHost{}
}

// GlobalTarget returns the Windsurf config dir under home.
func (windsurfHost) GlobalTarget(home string) string {
	return windsurfTarget(home)
}

// Install writes the shared skill and the cq MCP server entry.
func (windsurfHost) Install(ctx Context) ([]Change, error) {
	skill, err := writeManagedFiles(ctx.SkillsDir, map[string]string{
		filepath.Join("cq", "SKILL.md"): prompts.Skill(),
	}, ctx.DryRun)
	if err != nil {
		return nil, err
	}
	mcp, err := upsertJSONEntry(
		filepath.Join(ctx.Target, windsurfMCPFile),
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
func (windsurfHost) Name() string { return "windsurf" }

// SupportsProject reports that Windsurf is global-only.
func (windsurfHost) SupportsProject() bool { return false }

// Uninstall removes the cq MCP entry.
//
// NOTE: the skill lives in the shared commons (~/.agents/skills), which other
// hosts may also use, so uninstalling one host must not remove it; the shared
// skill is intentionally left in place.
func (windsurfHost) Uninstall(ctx Context) ([]Change, error) {
	mcp, err := removeJSONEntry(
		filepath.Join(ctx.Target, windsurfMCPFile),
		[]string{"mcpServers", "cq"},
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}
	return []Change{mcp}, nil
}
