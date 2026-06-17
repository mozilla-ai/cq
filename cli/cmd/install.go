package cmd

import (
	"fmt"
	"maps"
	"os"
	"slices"
	"strings"

	"github.com/spf13/cobra"

	"github.com/mozilla-ai/cq/cli/internal/install"
)

// installFlags holds the parsed flag state for one `cq install` invocation.
type installFlags struct {
	// dryRun reports planned changes without writing.
	dryRun bool

	// project installs into the given project directory; empty means global.
	project string

	// targets names the hosts to install into; set via the repeatable --target.
	targets targets

	// uninstall removes cq instead of installing it.
	uninstall bool
}

// targets is the set of hosts selected by the repeatable --target flag.
// It implements pflag.Value.
type targets map[install.Target]struct{}

// Set validates one --target occurrence, which may itself be a comma-separated
// list, and adds each target to the set, ignoring blanks.
func (t *targets) Set(v string) error {
	names := parseTargetNames(v)
	if len(names) == 0 {
		return nil
	}
	for _, name := range names {
		if !install.ValidTarget(name) {
			return fmt.Errorf("unknown target %s, supported: %s", name, install.AllowedTargets())
		}
		(*t)[name] = struct{}{}
	}
	return nil
}

// String renders the selected targets as a sorted, comma-separated list.
func (t targets) String() string {
	return t.names().String()
}

// Type names the value kind shown in help output.
func (t targets) Type() string {
	return "target"
}

// names returns the selected targets as a sorted set.
func (t targets) names() install.Targets {
	return install.Targets(slices.Sorted(maps.Keys(t)))
}

// NewInstallCmd returns the install command.
func NewInstallCmd() *cobra.Command {
	f := &installFlags{
		targets: targets{},
	}
	cmd := &cobra.Command{
		Use:   "install",
		Short: "Install cq into a coding-agent host.",
		Long: "Install cq into one or more coding-agent hosts (skill, MCP " +
			"configuration, and any host-specific assets). Re-running is " +
			"idempotent; pass --uninstall to remove.",
		RunE: func(cmd *cobra.Command, _ []string) error {
			return runInstallCmd(cmd, f)
		},
	}
	flags := cmd.Flags()
	flags.BoolVar(&f.dryRun, "dry-run", false, "report planned changes without writing")
	flags.StringVar(&f.project, "project", "", "install into the given project directory rather than globally")
	flags.Var(&f.targets, "target", fmt.Sprintf(
		"coding-agent host to install into; repeatable (supported: %s)",
		install.AllowedTargets(),
	))
	flags.BoolVar(&f.uninstall, "uninstall", false, "remove cq from the selected hosts")
	return cmd
}

// parseTargetNames splits, trims, lowercases, and dedupes the raw flag value,
// discarding blanks.
func parseTargetNames(v string) []install.Target {
	var names []install.Target
	seen := map[install.Target]struct{}{}
	for _, raw := range strings.Split(v, ",") {
		name := install.Target(strings.ToLower(strings.TrimSpace(raw)))
		if name == "" {
			continue
		}
		if _, dup := seen[name]; dup {
			continue
		}
		seen[name] = struct{}{}
		names = append(names, name)
	}
	return names
}

// printChanges writes a per-host summary of applied changes.
func printChanges(cmd *cobra.Command, host install.Target, changes []install.Change) {
	marker := map[install.Action]string{
		install.ActionCreated:   "+",
		install.ActionUpdated:   "~",
		install.ActionUnchanged: "=",
		install.ActionRemoved:   "-",
		install.ActionSkipped:   "!",
	}
	_, _ = fmt.Fprintf(cmd.OutOrStdout(), "[%s]\n", host)
	for _, c := range changes {
		suffix := ""
		if c.Detail != "" {
			suffix = "  (" + c.Detail + ")"
		}
		_, _ = fmt.Fprintf(cmd.OutOrStdout(), "  %s %s%s\n", marker[c.Action], c.Path, suffix)
	}
}

// runInstallCmd resolves the selected hosts and applies the requested action.
func runInstallCmd(cmd *cobra.Command, f *installFlags) error {
	hosts := install.SelectHosts(f.targets.names())
	if len(hosts) < 1 {
		return fmt.Errorf("select at least one --target (one of: %s)", install.AllowedTargets())
	}

	home, err := os.UserHomeDir()
	if err != nil {
		return fmt.Errorf("resolving home directory: %w", err)
	}
	binary, err := install.BinaryPath()
	if err != nil {
		return fmt.Errorf("resolving binary path: %w", err)
	}

	for _, h := range hosts {
		if f.project != "" && !h.SupportsProject() {
			return fmt.Errorf("host %s does not support project installs", h.Name())
		}
		ctx := install.Context{
			Target:     h.GlobalTarget(home),
			SkillsDir:  install.SharedSkillsDir(home),
			BinaryPath: binary,
			DryRun:     f.dryRun,
		}
		var changes []install.Change
		if f.uninstall {
			changes, err = h.Uninstall(ctx)
		} else {
			changes, err = h.Install(ctx)
		}
		if err != nil {
			return fmt.Errorf("%s: %w", h.Name(), err)
		}
		printChanges(cmd, h.Name(), changes)
	}
	return nil
}
