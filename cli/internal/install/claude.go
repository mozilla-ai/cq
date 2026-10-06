package install

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"slices"
	"strings"
)

const (
	// claudeCLI is the command name for the Claude Code CLI.
	claudeCLI = "claude"

	// claudeMarketplaceID is the plugin and marketplace name that the `claude plugin` commands use.
	claudeMarketplaceID = "cq"

	// claudeMarketplaceSource is the GitHub source slug used by
	// `claude plugin marketplace add`.
	claudeMarketplaceSource = "mozilla-ai/cq"
)

const (
	// claudeMarketplaceNotConfigured reports that the requested settings scope does not declare the marketplace.
	claudeMarketplaceNotConfigured claudeFailureCode = "not_configured"

	// claudePluginNotInstalled reports that the plugin is not installed in any scope.
	claudePluginNotInstalled claudeFailureCode = "not_installed"

	// claudePluginNotInstalledAtScope reports that the plugin is installed only in another scope.
	claudePluginNotInstalledAtScope claudeFailureCode = "not_installed_at_scope"
)

// claudeFailureCode is a failure code that `claude plugin --json` reports.
type claudeFailureCode string

// claudeHost installs the cq plugin into Claude Code via the marketplace CLI.
//
// Unlike the other adapters, Claude Code manages its own plugin config through
// `claude plugin marketplace` subcommands, so this adapter is a thin shell-out
// rather than a filesystem writer.
type claudeHost struct {
	// lookPath resolves a binary on PATH.
	//
	// Nil uses exec.LookPath.
	lookPath func(file string) (string, error)

	// run executes an external command and returns its standard output.
	//
	// Nil uses execRun.
	run func(name string, args ...string) ([]byte, error)
}

// claudeRemoval is one uninstall command and the failure codes that mean its target is already absent.
type claudeRemoval struct {
	// absent lists the failure codes reported when there is nothing to remove.
	absent []claudeFailureCode

	// args are the arguments passed to the claude CLI.
	args []string

	// path names the removed item in the reported change.
	path string
}

// claudeResult is the machine-readable result line of a `claude plugin --json` command.
type claudeResult struct {
	// FailureCode is empty when the command succeeded.
	FailureCode claudeFailureCode `json:"failureCode"` //nolint:tagliatelle // Claude Code defines this field name.
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
		{"plugin", "marketplace", "add", claudeMarketplaceSource},
		{"plugin", "install", claudeMarketplaceID},
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

// Uninstall runs `claude plugin uninstall` and `claude plugin marketplace remove`.
//
// An item that is already absent is reported unchanged, so repeated uninstalls succeed.
// NOTE: Removing the marketplace leaves the plugin enabled when another settings scope still declares the marketplace,
// so the plugin is uninstalled first.
func (h claudeHost) Uninstall(ctx Context) ([]Change, error) {
	if err := h.requireCLI(ctx.DryRun); err != nil {
		return nil, err
	}
	removals := []claudeRemoval{
		{
			absent: []claudeFailureCode{claudePluginNotInstalled, claudePluginNotInstalledAtScope},
			args:   []string{"plugin", "uninstall", claudeMarketplaceID, "--json"},
			path:   "claude plugin",
		},
		{
			absent: []claudeFailureCode{claudeMarketplaceNotConfigured},
			args:   []string{"plugin", "marketplace", "remove", claudeMarketplaceID, "--json"},
			path:   "claude marketplace",
		},
	}
	changes := make([]Change, 0, len(removals))
	for _, r := range removals {
		c, err := h.remove(r, ctx.DryRun)
		if err != nil {
			return nil, err
		}
		changes = append(changes, c)
	}
	return changes, nil
}

// remove runs one uninstall command, treating an already-absent target as unchanged.
func (h claudeHost) remove(r claudeRemoval, dryRun bool) (Change, error) {
	if dryRun {
		return Change{Action: ActionRemoved, Path: r.path}, nil
	}
	out, err := h.runner()(claudeCLI, r.args...)
	if err == nil {
		return Change{Action: ActionRemoved, Path: r.path}, nil
	}
	if slices.Contains(r.absent, parseClaudeFailureCode(out)) {
		return Change{Action: ActionUnchanged, Path: r.path}, nil
	}
	return Change{}, err
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

// runAll executes each claude CLI argument list in sequence, skipping all in dry-run mode.
func (h claudeHost) runAll(commands [][]string, dryRun bool) error {
	if dryRun {
		return nil
	}
	runner := h.runner()
	for _, args := range commands {
		if _, err := runner(claudeCLI, args...); err != nil {
			return err
		}
	}
	return nil
}

// runner returns the command executor, defaulting to exec.Command when none
// was injected.
func (h claudeHost) runner() func(string, ...string) ([]byte, error) {
	if h.run != nil {
		return h.run
	}
	return execRun
}

// execRun runs an external command and returns its standard output.
//
// A non-zero exit returns the standard output with a descriptive error.
func execRun(name string, args ...string) ([]byte, error) {
	cmd := exec.Command(name, args...)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		detail := strings.TrimSpace(stderr.String())
		if detail == "" {
			detail = strings.TrimSpace(string(out))
		}
		if detail != "" {
			return out, fmt.Errorf("running %s: %w\n%s", strings.Join(cmd.Args, " "), err, detail)
		}
		return out, fmt.Errorf("running %s: %w", strings.Join(cmd.Args, " "), err)
	}
	return out, nil
}

// parseClaudeFailureCode returns the failure code from the last line of `claude plugin --json` output.
//
// It returns an empty code when that line is not a machine-readable result.
func parseClaudeFailureCode(out []byte) claudeFailureCode {
	last := bytes.TrimSpace(out)
	if i := bytes.LastIndexByte(last, '\n'); i >= 0 {
		last = last[i+1:]
	}
	var r claudeResult
	if err := json.Unmarshal(last, &r); err != nil {
		return ""
	}
	return r.FailureCode
}
