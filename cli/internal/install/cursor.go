package install

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/mozilla-ai/cq/sdk/go/prompts"

	"github.com/mozilla-ai/cq/cli/internal/hook"
)

const (
	// cursorMCPFile is the MCP configuration file Cursor reads.
	cursorMCPFile = "mcp.json"

	// cursorHooksFile is the lifecycle-hook configuration file Cursor reads.
	cursorHooksFile = "hooks.json"

	// cursorStateDir holds the cq hook's cross-event state within the target.
	cursorStateDir = "cq-hook-state"

	// cursorRule is the always-applied Cursor rule pointing agents at the cq skill.
	cursorRule = "---\n" +
		"description: cq shared knowledge commons\n" +
		"alwaysApply: true\n" +
		"---\n\n" +
		"Before starting any implementation task, load the `cq` skill and follow its Core Protocol.\n"
)

// cursorRuleRelPath is the always-applied rule file, relative to the target.
var cursorRuleRelPath = filepath.Join("rules", "cq.mdc")

// cursorHookModes maps each Cursor lifecycle event (the hooks.json key) to the
// canonical cq hook mode passed to `cq _hook --mode`.
var cursorHookModes = []struct {
	// event is the Cursor hooks.json key for the lifecycle event.
	event string

	// mode is the canonical cq mode passed to cq _hook --mode.
	mode hook.Mode
}{
	{"sessionStart", hook.ModeSessionStart},
	{"postToolUseFailure", hook.ModePostToolUseFailure},
	{"postToolUse", hook.ModePostToolUse},
	{"stop", hook.ModeStop},
}

// cursorHost installs cq into the Cursor editor: the shared skill, the MCP
// server entry, an always-applied rule, and the lifecycle hooks.
//
// Cursor stores its config under <home>/.cursor on every platform and is
// global-only; it reads skills from the shared commons.
type cursorHost struct{}

// GlobalTarget returns the Cursor config dir under home.
func (cursorHost) GlobalTarget(home string) string {
	return cursorTarget(home)
}

// Install writes the shared skill, the MCP entry, the rule, and the hooks.
func (cursorHost) Install(ctx Context) ([]Change, error) {
	skill, err := writeManagedFiles(ctx.SkillsDir, map[string]string{
		filepath.Join("cq", "SKILL.md"): prompts.Skill(),
	}, ctx.DryRun)
	if err != nil {
		return nil, err
	}
	changes := []Change{skill}

	mcp, err := upsertJSONEntry(
		filepath.Join(ctx.Target, cursorMCPFile),
		[]string{"mcpServers", "cq"},
		map[string]any{"command": ctx.BinaryPath, "args": []any{"mcp"}},
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}
	changes = append(changes, mcp)

	rule, err := writeIfMissing(filepath.Join(ctx.Target, cursorRuleRelPath), cursorRule, ctx.DryRun)
	if err != nil {
		return nil, err
	}
	changes = append(changes, rule)

	for _, hm := range cursorHookModes {
		h, err := upsertHookEntry(
			filepath.Join(ctx.Target, cursorHooksFile),
			hm.event,
			cursorHookCommand(ctx, hm.mode),
			ctx.DryRun,
		)
		if err != nil {
			return nil, err
		}
		changes = append(changes, h)
	}
	return changes, nil
}

// Name returns the host identifier.
func (cursorHost) Name() Target { return TargetCursor }

// SupportsProject reports that Cursor is installed globally in this phase.
func (cursorHost) SupportsProject() bool { return false }

// Uninstall removes the MCP entry, the rule (when unmodified), the hook
// entries, and the hook state dir.
//
// NOTE: the skill lives in the shared commons (~/.agents/skills), which other
// hosts may also use, so it is intentionally left in place.
func (cursorHost) Uninstall(ctx Context) ([]Change, error) {
	mcp, err := removeJSONEntry(
		filepath.Join(ctx.Target, cursorMCPFile),
		[]string{"mcpServers", "cq"},
		ctx.DryRun,
	)
	if err != nil {
		return nil, err
	}
	changes := []Change{mcp}

	rule, err := removeOwnedFile(filepath.Join(ctx.Target, cursorRuleRelPath), sha256Hex(cursorRule), ctx.DryRun)
	if err != nil {
		return nil, err
	}
	changes = append(changes, rule)

	for _, hm := range cursorHookModes {
		h, err := removeHookEntry(
			filepath.Join(ctx.Target, cursorHooksFile),
			hm.event,
			cursorHookCommand(ctx, hm.mode),
			ctx.DryRun,
		)
		if err != nil {
			return nil, err
		}
		changes = append(changes, h)
	}

	stateChange, err := removeCursorStateDir(ctx)
	if err != nil {
		return nil, err
	}
	changes = append(changes, stateChange)
	return changes, nil
}

// cursorHookCommand builds the shell command Cursor runs for one hook event:
// this binary's hidden _hook handler, with the resolved state dir.
func cursorHookCommand(ctx Context, mode hook.Mode) string {
	return shellJoin(
		ctx.BinaryPath,
		"_hook",
		"--host", string(hook.HostCursor),
		"--mode", string(mode),
		"--state-dir", filepath.Join(ctx.Target, cursorStateDir),
	)
}

// removeCursorStateDir deletes the hook state dir, which the installer and the
// cq hook own entirely (no user files are ever written there).
func removeCursorStateDir(ctx Context) (Change, error) {
	dir := filepath.Join(ctx.Target, cursorStateDir)
	if _, err := os.Stat(dir); os.IsNotExist(err) {
		return Change{Action: ActionUnchanged, Path: dir}, nil
	} else if err != nil {
		return Change{}, fmt.Errorf("checking hook state directory: %w", err)
	}
	if !ctx.DryRun {
		if err := os.RemoveAll(dir); err != nil {
			return Change{}, fmt.Errorf("removing hook state directory: %w", err)
		}
	}
	return Change{Action: ActionRemoved, Path: dir}, nil
}
