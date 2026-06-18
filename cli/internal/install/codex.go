package install

import (
	"path/filepath"

	"github.com/mozilla-ai/cq/sdk/go/prompts"
)

const (
	// codexAgentsFile is the always-loaded instruction file for Codex.
	codexAgentsFile = "AGENTS.md"

	// codexConfigFile is the TOML configuration file Codex reads.
	codexConfigFile = "config.toml"

	// codexMCPSection is the dotted TOML key path for the cq MCP server entry.
	codexMCPSection = "mcp_servers.cq"
)

// codexAgentsBlock is the delimited block written into AGENTS.md.
var codexAgentsBlock = cqBlock.start + "\n## CQ\n\nBefore starting any implementation task, load the `cq` skill and follow its Core Protocol.\n" + cqBlock.end

// codexHost installs cq into the OpenAI Codex CLI: the shared skill, the MCP
// server entry in config.toml, and an AGENTS.md instruction block.
//
// Codex reads config from ~/.codex/config.toml (TOML format) and instructions
// from ~/.codex/AGENTS.md.
type codexHost struct{}

// GlobalTarget returns the Codex config directory under home.
func (codexHost) GlobalTarget(home string) string {
	return codexTarget(home)
}

// Install writes the shared skill, the MCP entry, and the AGENTS.md block.
func (codexHost) Install(ctx Context) ([]Change, error) {
	skill, err := writeManagedFiles(ctx.SkillsDir, map[string]string{
		filepath.Join("cq", "SKILL.md"): prompts.Skill(),
	}, ctx.DryRun)
	if err != nil {
		return nil, err
	}

	mcp, err := upsertTOMLSection(
		filepath.Join(ctx.Target, codexConfigFile),
		codexMCPSection,
		map[string]any{
			"command": ctx.BinaryPath,
			"args":    []any{"mcp"},
		},
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}

	agents, err := upsertMarkdownBlock(
		filepath.Join(ctx.Target, codexAgentsFile),
		cqBlock,
		codexAgentsBlock,
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}

	return []Change{skill, mcp, agents}, nil
}

// Name returns the host identifier.
func (codexHost) Name() Target { return TargetCodex }

// SupportsProject reports that Codex is global-only in this phase.
func (codexHost) SupportsProject() bool { return false }

// Uninstall removes the MCP entry and the AGENTS.md block.
//
// NOTE: the skill lives in the shared commons (~/.agents/skills), which other
// hosts may also use, so it is intentionally left in place.
func (codexHost) Uninstall(ctx Context) ([]Change, error) {
	mcp, err := removeTOMLSection(
		filepath.Join(ctx.Target, codexConfigFile),
		codexMCPSection,
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}

	agents, err := removeMarkdownBlock(
		filepath.Join(ctx.Target, codexAgentsFile),
		cqBlock,
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}

	return []Change{mcp, agents}, nil
}
