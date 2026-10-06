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

const (
	// claudeScopeProject declares cq in a project's shared settings.
	claudeScopeProject claudeScope = "project"

	// claudeScopeUser declares cq in the user's settings.
	claudeScopeUser claudeScope = "user"
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

	// run executes an external command in dir and returns its standard output.
	//
	// Nil uses execRun.
	run func(dir string, name string, args ...string) ([]byte, error)
}

// claudeResult is the machine-readable result line of a `claude plugin --json` command.
type claudeResult struct {
	// FailureCode is empty when the command succeeded.
	FailureCode claudeFailureCode `json:"failureCode"` //nolint:tagliatelle // Claude Code defines this field name.
}

// claudeScope is a Claude Code settings scope that a plugin is declared in.
type claudeScope string

// claudeStep is one claude CLI command and the item it reports a change for.
type claudeStep struct {
	// absent lists the failure codes that mean the item is already absent.
	absent []claudeFailureCode

	// args are the arguments passed to the claude CLI.
	args []string

	// path names the item in the reported change.
	path string
}

// GlobalTarget returns a sentinel path.
//
// Claude Code manages its own config; the install package never writes to
// this path.
func (claudeHost) GlobalTarget(string) string {
	return os.DevNull
}

// Install declares the cq marketplace and installs the cq plugin in Claude Code.
//
// A global install uses the user scope, and a project install uses the project scope.
// NOTE: The claude CLI reports success whether or not cq was already present,
// so a repeated install still reports each item as created.
func (h claudeHost) Install(ctx Context) ([]Change, error) {
	scope := string(claudeScopeFor(ctx))
	return h.applyAll(ctx, []claudeStep{
		{
			args: []string{"plugin", "marketplace", "add", claudeMarketplaceSource, "--scope", scope},
			path: "claude marketplace",
		},
		{
			args: []string{"plugin", "install", claudeMarketplaceID, "--scope", scope},
			path: "claude plugin",
		},
	}, ActionCreated)
}

// Name returns the host identifier.
func (claudeHost) Name() Target { return TargetClaude }

// SupportsProject reports that Claude Code supports project installs.
func (claudeHost) SupportsProject() bool { return true }

// Uninstall removes the cq plugin and marketplace from the scope that Install uses.
//
// An item that is already absent is reported unchanged, so repeated uninstalls succeed.
// NOTE: Removing the marketplace leaves the plugin enabled when another settings scope still declares the marketplace,
// so the plugin is uninstalled first.
func (h claudeHost) Uninstall(ctx Context) ([]Change, error) {
	scope := string(claudeScopeFor(ctx))
	return h.applyAll(ctx, []claudeStep{
		{
			absent: []claudeFailureCode{claudePluginNotInstalled, claudePluginNotInstalledAtScope},
			args:   []string{"plugin", "uninstall", claudeMarketplaceID, "--scope", scope, "--json"},
			path:   "claude plugin",
		},
		{
			absent: []claudeFailureCode{claudeMarketplaceNotConfigured},
			args:   []string{"plugin", "marketplace", "remove", claudeMarketplaceID, "--scope", scope, "--json"},
			path:   "claude marketplace",
		},
	}, ActionRemoved)
}

// apply runs one step and reports action, or reports the item unchanged when it is already absent.
func (h claudeHost) apply(ctx Context, step claudeStep, action Action) (Change, error) {
	change := Change{Action: action, Path: step.path, Detail: claudeScopeDetail(ctx)}
	if ctx.DryRun {
		return change, nil
	}
	out, err := h.runner()(ctx.ProjectDir, claudeCLI, step.args...)
	if err == nil {
		return change, nil
	}
	if slices.Contains(step.absent, parseClaudeFailureCode(out)) {
		change.Action = ActionUnchanged
		return change, nil
	}
	return Change{}, err
}

// applyAll runs each step in order and stops at the first failure.
func (h claudeHost) applyAll(ctx Context, steps []claudeStep, action Action) ([]Change, error) {
	if err := h.requireCLI(); err != nil {
		return nil, err
	}
	changes := make([]Change, 0, len(steps))
	for _, step := range steps {
		c, err := h.apply(ctx, step, action)
		if err != nil {
			return nil, err
		}
		changes = append(changes, c)
	}
	return changes, nil
}

// requireCLI verifies the claude CLI is on PATH, so a dry run fails where a real run would.
func (h claudeHost) requireCLI() error {
	lookup := h.lookPath
	if lookup == nil {
		lookup = exec.LookPath
	}
	if _, err := lookup(claudeCLI); err != nil {
		return fmt.Errorf("claude CLI not found on PATH; install Claude Code first: %w", err)
	}
	return nil
}

// runner returns the command executor, defaulting to execRun when none was injected.
func (h claudeHost) runner() func(string, string, ...string) ([]byte, error) {
	if h.run != nil {
		return h.run
	}
	return execRun
}

// claudeScopeDetail describes the settings scope that a change applies to.
func claudeScopeDetail(ctx Context) string {
	scope := claudeScopeFor(ctx)
	if scope == claudeScopeProject {
		return fmt.Sprintf("%s scope: %s", scope, ctx.ProjectDir)
	}
	return fmt.Sprintf("%s scope", scope)
}

// claudeScopeFor returns the settings scope for a global or project install.
func claudeScopeFor(ctx Context) claudeScope {
	if ctx.ProjectDir != "" {
		return claudeScopeProject
	}
	return claudeScopeUser
}

// execRun runs an external command in dir and returns its standard output.
//
// An empty dir runs the command in the current directory.
// A non-zero exit returns the standard output with a descriptive error.
func execRun(dir string, name string, args ...string) ([]byte, error) {
	cmd := exec.Command(name, args...)
	cmd.Dir = dir
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
