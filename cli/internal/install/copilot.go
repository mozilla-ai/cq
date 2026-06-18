package install

import (
	"path/filepath"

	"github.com/mozilla-ai/cq/sdk/go/prompts"
)

const (
	// copilotInstruction is the global instruction file content telling Copilot
	// to load the cq skill before starting work.
	copilotInstruction = "Before starting any implementation task, load the `cq` skill and follow its Core Protocol.\n"

	// copilotInstructionFile is the cq instruction file written into the
	// global Copilot instructions directory.
	copilotInstructionFile = "cq.md"

	// copilotInstructionsDir is the user-level directory Copilot reads for
	// global custom instructions.
	copilotInstructionsDir = ".copilot/instructions"

	// copilotMCPFile is the MCP configuration file VSCode reads.
	copilotMCPFile = "mcp.json"
)

// copilotHost installs cq into GitHub Copilot in VSCode: the shared skill,
// the MCP server entry, and a global instruction file.
//
// Copilot reads MCP config from <vscode-user-dir>/mcp.json with a top-level
// "servers" key (not "mcpServers").
// Skills are read from ~/.agents/skills/ (the shared commons).
// Global instructions are read from ~/.copilot/instructions/.
//
// NOTE: targets the default VSCode profile only.
// Users with custom profiles or VSCode Insiders need to configure manually.
type copilotHost struct{}

// GlobalTarget returns the VSCode user config directory under home.
func (copilotHost) GlobalTarget(home string) string {
	return copilotTarget(home)
}

// Install writes the shared skill, the cq MCP server entry, and the global
// instruction file.
func (copilotHost) Install(ctx Context) ([]Change, error) {
	skill, err := writeManagedFiles(ctx.SkillsDir, map[string]string{
		filepath.Join("cq", "SKILL.md"): prompts.Skill(),
	}, ctx.DryRun)
	if err != nil {
		return nil, err
	}

	mcp, err := upsertJSONEntry(
		filepath.Join(ctx.Target, copilotMCPFile),
		[]string{"servers", "cq"},
		map[string]any{
			"type":    "stdio",
			"command": ctx.BinaryPath,
			"args":    []any{"mcp"},
		},
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}

	instruction, err := writeIfMissing(
		filepath.Join(ctx.Home, copilotInstructionsDir, copilotInstructionFile),
		copilotInstruction,
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}

	return []Change{skill, mcp, instruction}, nil
}

// Name returns the host identifier.
func (copilotHost) Name() Target { return TargetCopilot }

// SupportsProject reports that Copilot is global-only in this phase.
func (copilotHost) SupportsProject() bool { return false }

// Uninstall removes the cq MCP entry and the instruction file (when
// unmodified).
//
// NOTE: the skill lives in the shared commons (~/.agents/skills), which other
// hosts may also use, so it is intentionally left in place.
func (copilotHost) Uninstall(ctx Context) ([]Change, error) {
	mcp, err := removeJSONEntry(
		filepath.Join(ctx.Target, copilotMCPFile),
		[]string{"servers", "cq"},
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}

	instruction, err := removeOwnedFile(
		filepath.Join(ctx.Home, copilotInstructionsDir, copilotInstructionFile),
		sha256Hex(copilotInstruction),
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}

	return []Change{mcp, instruction}, nil
}
