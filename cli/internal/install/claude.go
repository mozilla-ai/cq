package install

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
)

const (
	// claudeCLI is the command name for the Claude Code CLI.
	claudeCLI = "claude"

	// claudeMarketplaceID is the plugin identifier used by
	// `claude plugin install` and `claude plugin marketplace remove`.
	claudeMarketplaceID = "cq"

	// claudeMarketplaceSource is the GitHub source slug used by
	// `claude plugin marketplace add`.
	claudeMarketplaceSource = "mozilla-ai/cq"
)

// claudeHost installs the cq plugin into Claude Code via the marketplace CLI.
//
// Unlike the other adapters, Claude Code manages its own plugin config through
// `claude plugin marketplace` subcommands, so this adapter is a thin shell-out
// rather than a filesystem writer.
type claudeHost struct {
	// lookPath resolves a binary on PATH.
	//
	// Nil uses the default (exec.LookPath); tests inject a stub.
	lookPath func(file string) (string, error)

	// run executes an external command.
	//
	// Nil uses the default (exec.Command); tests inject a stub.
	run func(name string, args ...string) error
}

// GlobalTarget returns a sentinel path.
//
// Claude Code manages its own config; the install package never writes to
// this path.
func (claudeHost) GlobalTarget(string) string {
	return os.DevNull
}

// Install runs `claude plugin marketplace add` and `claude plugin install`.
func (h claudeHost) Install(ctx Context) ([]Change, error) {
	if err := h.requireCLI(ctx.DryRun); err != nil {
		return nil, err
	}
	commands := [][]string{
		{claudeCLI, "plugin", "marketplace", "add", claudeMarketplaceSource},
		{claudeCLI, "plugin", "install", claudeMarketplaceID},
	}
	if err := h.runAll(commands, ctx.DryRun); err != nil {
		return nil, err
	}
	return []Change{{Action: ActionCreated, Path: "claude marketplace"}}, nil
}

// Name returns the host identifier.
func (claudeHost) Name() Target { return TargetClaude }

// SupportsProject reports that Claude Code is global-only.
func (claudeHost) SupportsProject() bool { return false }

// Uninstall runs `claude plugin marketplace remove`.
//
// Removing the marketplace entry unregisters the plugin as well, so no
// separate `claude plugin uninstall` call is needed.
func (h claudeHost) Uninstall(ctx Context) ([]Change, error) {
	if err := h.requireCLI(ctx.DryRun); err != nil {
		return nil, err
	}
	commands := [][]string{
		{claudeCLI, "plugin", "marketplace", "remove", claudeMarketplaceID},
	}
	if err := h.runAll(commands, ctx.DryRun); err != nil {
		return nil, err
	}
	return []Change{{Action: ActionRemoved, Path: "claude marketplace"}}, nil
}

// requireCLI verifies the claude CLI is on PATH.
func (h claudeHost) requireCLI(dryRun bool) error {
	if dryRun {
		return nil
	}
	lookup := h.lookPath
	if lookup == nil {
		lookup = exec.LookPath
	}
	if _, err := lookup(claudeCLI); err != nil {
		return fmt.Errorf("claude CLI not found on PATH; install Claude Code first: %w", err)
	}
	return nil
}

// runAll executes each command in sequence, skipping all in dry-run mode.
func (h claudeHost) runAll(commands [][]string, dryRun bool) error {
	if dryRun {
		return nil
	}
	runner := h.runner()
	for _, cmd := range commands {
		if err := runner(cmd[0], cmd[1:]...); err != nil {
			return err
		}
	}
	return nil
}

// runner returns the command executor, defaulting to exec.Command when none
// was injected.
func (h claudeHost) runner() func(string, ...string) error {
	if h.run != nil {
		return h.run
	}
	return execRun
}

// execRun runs an external command, returning a descriptive error on non-zero
// exit.
func execRun(name string, args ...string) error {
	cmd := exec.Command(name, args...)
	out, err := cmd.CombinedOutput()
	if err != nil {
		detail := strings.TrimSpace(string(out))
		if detail != "" {
			return fmt.Errorf("running %s: %w\n%s", strings.Join(cmd.Args, " "), err, detail)
		}
		return fmt.Errorf("running %s: %w", strings.Join(cmd.Args, " "), err)
	}
	return nil
}
