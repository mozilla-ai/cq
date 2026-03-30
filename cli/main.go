package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/mozilla-ai/cq/cli/cmd"
	"github.com/mozilla-ai/cq/cli/internal/version"
)

func main() {
	if err := execute(); err != nil {
		_, _ = fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}

func execute() error {
	rootCmd := newRootCmd()

	return rootCmd.Execute()
}

func newRootCmd() *cobra.Command {
	rootCmd := &cobra.Command{
		Use:           "cq",
		Short:         "Shared agent knowledge commons.",
		Long:          "cq is a shared knowledge store that helps agents avoid known pitfalls.",
		SilenceUsage:  true,
		SilenceErrors: true,
	}

	rootCmd.SetVersionTemplate("{{.Version}}\n")
	rootCmd.Version = version.String()

	rootCmd.AddGroup(&cobra.Group{ID: "core", Title: "Core Commands:"})

	for _, fn := range []func() *cobra.Command{
		cmd.NewConfirmCmd,
		cmd.NewFlagCmd,
		cmd.NewMCPCmd,
		cmd.NewPromptCmd,
		cmd.NewProposeCmd,
		cmd.NewQueryCmd,
		cmd.NewStatusCmd,
	} {
		c := fn()
		c.GroupID = "core"
		rootCmd.AddCommand(c)
	}

	rootCmd.AddGroup(&cobra.Group{ID: "system", Title: "System Commands:"})
	rootCmd.SetHelpCommandGroupID("system")
	rootCmd.SetCompletionCommandGroupID("system")

	return rootCmd
}
