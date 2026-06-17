package install

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/mozilla-ai/cq/sdk/go/prompts"
)

const (
	// opencodeConfigFile is the main configuration file OpenCode reads.
	opencodeConfigFile = "opencode.json"

	// opencodeAgentsFile is the always-loaded instruction file for OpenCode.
	opencodeAgentsFile = "AGENTS.md"

	// opencodeCommandsDir holds command files within the OpenCode target.
	opencodeCommandsDir = "commands"

	// opencodeSchemaURL is seeded into a fresh opencode.json for editor
	// autocomplete and validation.
	opencodeSchemaURL = "https://opencode.ai/config.json"
)

// opencodeAgentsBlock is the delimited block written into AGENTS.md.
var opencodeAgentsBlock = cqBlock.start + "\n## CQ\n\nBefore starting any implementation task, load the `cq` skill and follow its Core Protocol.\n" + cqBlock.end

// opencodeCommands maps each command filename to the SDK accessor that
// returns its canonical Claude Code source.
var opencodeCommands = []struct {
	file string
	body func() string
}{
	{"reflect.md", prompts.Reflect},
	{"status.md", prompts.Status},
}

// opencodeHost installs cq into the OpenCode editor: the shared skill, the
// MCP server entry, command files, and an AGENTS.md instruction block.
//
// OpenCode stores its config under ~/.config/opencode on every platform
// (overridable via OPENCODE_CONFIG_DIR) and is global-only in this phase.
type opencodeHost struct{}

// GlobalTarget returns the OpenCode config dir.
func (opencodeHost) GlobalTarget(home string) string {
	return opencodeTarget(home)
}

// Install writes the shared skill, the MCP entry, command files, and the
// AGENTS.md block.
func (opencodeHost) Install(ctx Context) ([]Change, error) {
	skill, err := writeManagedFiles(ctx.SkillsDir, map[string]string{
		filepath.Join("cq", "SKILL.md"): prompts.Skill(),
	}, ctx.DryRun)
	if err != nil {
		return nil, err
	}
	changes := []Change{skill}

	mcp, err := opencodeInstallMCP(ctx)
	if err != nil {
		return nil, err
	}
	changes = append(changes, mcp)

	cmds, err := opencodeInstallCommands(ctx)
	if err != nil {
		return nil, err
	}
	changes = append(changes, cmds)

	agents, err := upsertMarkdownBlock(
		filepath.Join(ctx.Target, opencodeAgentsFile),
		cqBlock,
		opencodeAgentsBlock,
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}
	changes = append(changes, agents)

	return changes, nil
}

// Name returns the host identifier.
func (opencodeHost) Name() Target { return TargetOpenCode }

// SupportsProject reports that OpenCode is installed globally in this phase.
func (opencodeHost) SupportsProject() bool { return false }

// Uninstall removes the MCP entry, command files, and the AGENTS.md block.
//
// NOTE: the skill lives in the shared commons (~/.agents/skills), which other
// hosts may also use, so it is intentionally left in place.
func (opencodeHost) Uninstall(ctx Context) ([]Change, error) {
	mcp, err := removeJSONEntry(
		filepath.Join(ctx.Target, opencodeConfigFile),
		[]string{"mcp", "cq"},
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}
	changes := []Change{mcp}

	commandsPath := filepath.Join(ctx.Target, opencodeCommandsDir)
	cmds, err := removeManagedFiles(commandsPath, ctx.DryRun)
	if err != nil {
		return nil, err
	}
	if cmds.Action == ActionRemoved && !ctx.DryRun {
		// Best-effort: remove the now-empty commands directory.
		_ = os.Remove(commandsPath)
	}
	changes = append(changes, cmds)

	agents, err := removeMarkdownBlock(
		filepath.Join(ctx.Target, opencodeAgentsFile),
		cqBlock,
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}
	changes = append(changes, agents)

	return changes, nil
}

// opencodeInstallMCP writes the MCP server entry, seeding $schema on fresh
// file creation only so editor autocomplete works from the first install.
func opencodeInstallMCP(ctx Context) (Change, error) {
	configPath := filepath.Join(ctx.Target, opencodeConfigFile)
	if err := seedOpenCodeSchema(configPath, ctx.DryRun); err != nil {
		return Change{}, err
	}
	return upsertJSONEntry(
		configPath,
		[]string{"mcp", "cq"},
		map[string]any{
			"type":    "local",
			"command": []any{ctx.BinaryPath, "mcp"},
		},
		ctx.DryRun,
	)
}

// seedOpenCodeSchema writes the $schema URL into a fresh opencode.json so
// OpenCode's editor autocomplete works from the first install.
//
// Existing files are left untouched so user overrides survive re-installs.
func seedOpenCodeSchema(configPath string, dryRun bool) error {
	_, err := os.Stat(configPath)
	if err == nil || dryRun {
		return nil
	}
	if !os.IsNotExist(err) {
		return fmt.Errorf("checking config file: %w", err)
	}
	if err := os.MkdirAll(filepath.Dir(configPath), 0o755); err != nil {
		return fmt.Errorf("creating config directory: %w", err)
	}
	return writeJSONObject(configPath, map[string]any{"$schema": opencodeSchemaURL})
}

// opencodeInstallCommands transforms and writes the command files into the
// target's commands directory, tracked by a manifest for idempotent updates
// and safe uninstall.
func opencodeInstallCommands(ctx Context) (Change, error) {
	files := make(map[string]string, len(opencodeCommands))
	for _, cmd := range opencodeCommands {
		files[cmd.file] = transformCommand(cmd.body())
	}
	return writeManagedFiles(
		filepath.Join(ctx.Target, opencodeCommandsDir),
		files,
		ctx.DryRun,
	)
}
