package cmd

import (
	"fmt"

	"github.com/spf13/cobra"

	"github.com/mozilla-ai/cq/cli/internal/hook"
)

// NewHookCmd returns the hidden command a host's hook configuration invokes for
// each lifecycle event. It binds its flags into a hook.Invocation and runs it.
//
// NOTE: this command is internal wiring written into host config by
// `cq install`; it is not part of the user-facing command surface.
func NewHookCmd() *cobra.Command {
	var inv hook.Invocation
	cmd := &cobra.Command{
		Use:    "_hook",
		Short:  "Handle a coding-agent lifecycle hook event.",
		Hidden: true,
		Args:   cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if err := hook.Run(inv, cmd.InOrStdin(), cmd.OutOrStdout()); err != nil {
				_, _ = fmt.Fprintf(cmd.ErrOrStderr(), "cq: hook internal error: %v\n", err)
			}
			return nil
		},
	}
	flags := cmd.Flags()
	flags.Var(&inv.Host, "host", fmt.Sprintf("host whose hook fired (one of: %s)", hook.AllowedHosts()))
	flags.Var(&inv.Mode, "mode", fmt.Sprintf("lifecycle event mode (one of: %s)", hook.AllowedModes()))
	flags.StringVar(&inv.StateDir, "state-dir", "", "directory for cross-event hook state")
	_ = cmd.MarkFlagRequired("host")
	_ = cmd.MarkFlagRequired("mode")
	_ = cmd.MarkFlagRequired("state-dir")
	return cmd
}
