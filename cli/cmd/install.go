package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/mozilla-ai/cq/cli/internal/install"
)

// installFlags holds the parsed flag state for one `cq install` invocation.
type installFlags struct {
	// dryRun reports planned changes without writing.
	dryRun bool

	// project installs into the given project directory; empty means global.
	project string

	// uninstall removes cq instead of installing it.
	uninstall bool

	// windsurf targets the Windsurf host.
	windsurf bool
}

// NewInstallCmd returns the install command.
func NewInstallCmd() *cobra.Command {
	f := &installFlags{}
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
	flags.BoolVar(&f.uninstall, "uninstall", false, "remove cq from the selected hosts")
	flags.BoolVar(&f.windsurf, "windsurf", false, "target the Windsurf host")
	return cmd
}

// runInstallCmd resolves the selected hosts and applies the requested action.
func runInstallCmd(cmd *cobra.Command, f *installFlags) error {
	hosts := install.SelectHosts(install.Selection{Windsurf: f.windsurf})
	if len(hosts) == 0 {
		return fmt.Errorf("select at least one host (e.g. --windsurf)")
	}

	home, err := os.UserHomeDir()
	if err != nil {
		return fmt.Errorf("resolving home directory: %w", err)
	}
	var binary string
	if !f.uninstall {
		// Uninstall does not write the binary path into host config, so only
		// resolve it for installs.
		binary, err = install.BinaryPath()
		if err != nil {
			return fmt.Errorf("resolving binary path: %w", err)
		}
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

// printChanges writes a per-host summary of applied changes.
func printChanges(cmd *cobra.Command, host string, changes []install.Change) {
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
