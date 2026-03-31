package cmd

import (
	"encoding/json"
	"fmt"

	"github.com/spf13/cobra"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// NewPromptCmd returns the prompt command.
func NewPromptCmd() *cobra.Command {
	var format string

	cmd := &cobra.Command{
		Use:   "prompt",
		Short: "Print the agent protocol prompt.",
		Long: "Print the full cq agent protocol prompt for injection into an " +
			"agent system prompt. Use this when integrating cq into agent " +
			"frameworks that do not have the cq plugin installed.",
		RunE: func(cmd *cobra.Command, _ []string) error {
			if format != "text" && format != "json" {
				return fmt.Errorf("unsupported format '%s': must be text or json", format)
			}

			prompt := cq.Prompt()

			if format == "json" {
				enc := json.NewEncoder(cmd.OutOrStdout())
				enc.SetIndent("", "  ")

				return enc.Encode(map[string]string{"prompt": prompt})
			}

			_, _ = fmt.Fprint(cmd.OutOrStdout(), prompt)

			return nil
		},
	}

	cmd.Flags().StringVar(&format, "format", "text", "Output format: text or json")

	return cmd
}
