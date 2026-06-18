package install

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/mozilla-ai/cq/sdk/go/prompts"
)

const (
	// piAgentsFile is the always-loaded instruction file for Pi.
	piAgentsFile = "AGENTS.md"

	// piPromptsDir holds transformed prompt files within the Pi target.
	piPromptsDir = "prompts"
)

// piPrompts maps each prompt filename (with the cq- prefix Pi expects) to the
// SDK accessor that returns its canonical source.
var piPrompts = []struct {
	file string
	body func() string
}{
	{"cq-reflect.md", prompts.Reflect},
	{"cq-status.md", prompts.Status},
}

// piHost installs cq into the Pi coding agent: the shared skill, transformed
// prompt files, and an AGENTS.md block that maps each cq action to a CLI
// invocation.
//
// Pi has no native MCP, so the AGENTS.md block instructs the agent to run the
// cq binary directly through its shell tool.
type piHost struct{}

// GlobalTarget returns the Pi global config dir under home.
//
// NOTE: Pi's global path has an extra "agent" segment (~/.pi/agent) that the
// per-project path (.pi/) does not.
func (piHost) GlobalTarget(home string) string {
	return piTarget(home)
}

// Install writes the shared skill, prompt files, and the AGENTS.md block.
func (piHost) Install(ctx Context) ([]Change, error) {
	skill, err := writeManagedFiles(ctx.SkillsDir, map[string]string{
		filepath.Join("cq", "SKILL.md"): prompts.Skill(),
	}, ctx.DryRun)
	if err != nil {
		return nil, err
	}
	changes := []Change{skill}

	promptChanges, err := piInstallPrompts(ctx)
	if err != nil {
		return nil, err
	}
	changes = append(changes, promptChanges)

	agents, err := upsertMarkdownBlock(
		filepath.Join(ctx.Target, piAgentsFile),
		cqBlock,
		piAgentsBlock(ctx.BinaryPath, ctx.CLIVerbs),
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}
	changes = append(changes, agents)

	return changes, nil
}

// Name returns the host identifier.
func (piHost) Name() Target { return TargetPi }

// SupportsProject reports that Pi is installed globally in this phase.
func (piHost) SupportsProject() bool { return false }

// Uninstall removes the prompt files and the AGENTS.md block.
//
// NOTE: the skill lives in the shared commons (~/.agents/skills), which other
// hosts may also use, so it is intentionally left in place.
func (piHost) Uninstall(ctx Context) ([]Change, error) {
	promptsPath := filepath.Join(ctx.Target, piPromptsDir)
	promptChanges, err := removeManagedFiles(promptsPath, ctx.DryRun)
	if err != nil {
		return nil, err
	}
	if promptChanges.Action == ActionRemoved && !ctx.DryRun {
		// Best-effort: remove the now-empty prompts directory.
		_ = os.Remove(promptsPath)
	}
	changes := []Change{promptChanges}

	agents, err := removeMarkdownBlock(
		filepath.Join(ctx.Target, piAgentsFile),
		cqBlock,
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}
	changes = append(changes, agents)

	return changes, nil
}

// piAgentsBlock returns the delimited AGENTS.md block that maps each cq action
// to a CLI invocation using the given binary path and verb definitions.
func piAgentsBlock(binaryPath string, verbs []CLIVerb) string {
	var mapping strings.Builder
	for _, v := range verbs {
		fmt.Fprintf(&mapping, "### %s %s\n\n", binaryPath, v.UseLine)
		if v.FlagUsages != "" {
			fmt.Fprintf(&mapping, "```\n%s```\n\n", v.FlagUsages)
		}
	}

	return cqBlock.start + "\n## CQ\n\n" +
		"Before starting any implementation task, load the `cq` skill and follow its Core Protocol.\n\n" +
		"This runtime has no cq MCP server.\n" +
		"The cq skill and `/cq-*` commands describe the protocol using MCP-tool wording; in this runtime,\n" +
		"perform every cq action by running the cq CLI through your shell.\n" +
		"Parse `--format json` output for the commands that support it (query, propose, status); confirm and\n" +
		"flag return plain text.\n" +
		"The cq binary is: `" + binaryPath + "`.\n\n" +
		mapping.String() +
		cqBlock.end
}

// piInstallPrompts transforms and writes the prompt files into the target's
// prompts directory, tracked by a manifest for idempotent updates and safe
// uninstall.
func piInstallPrompts(ctx Context) (Change, error) {
	files := make(map[string]string, len(piPrompts))
	for _, p := range piPrompts {
		files[p.file] = transformPiCommand(p.body())
	}
	return writeManagedFiles(
		filepath.Join(ctx.Target, piPromptsDir),
		files,
		ctx.DryRun,
	)
}

// transformPiCommand converts a Claude Code command file to Pi format by
// stripping the `name:` frontmatter line and rewriting `/cq:` references to
// `/cq-` so the body matches Pi's filename-derived command names.
//
// Returns the source unchanged when YAML frontmatter is absent or unclosed.
func transformPiCommand(source string) string {
	lines := strings.SplitAfter(source, "\n")
	if len(lines) == 0 || strings.TrimRight(lines[0], "\r\n") != "---" {
		return source
	}

	out := []string{lines[0]}
	inFrontmatter := true
	closed := false
	for _, line := range lines[1:] {
		if inFrontmatter && strings.TrimRight(line, "\r\n") == "---" {
			out = append(out, line)
			inFrontmatter = false
			closed = true
			continue
		}
		if inFrontmatter && strings.HasPrefix(line, "name:") {
			continue
		}
		out = append(out, line)
	}

	if !closed {
		return source
	}
	return strings.ReplaceAll(strings.Join(out, ""), "/cq:", "/cq-")
}
