package cmd

import (
	"encoding/json"
	"fmt"

	"github.com/spf13/cobra"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// NewProposeCmd returns the propose command.
func NewProposeCmd() *cobra.Command {
	var (
		summary    string
		detail     string
		action     string
		domains    []string
		languages  []string
		frameworks []string
		pattern    string
		format     string
	)

	cmd := &cobra.Command{
		Use:   "propose",
		Short: "Propose a new knowledge unit.",
		RunE: func(cmd *cobra.Command, _ []string) error {
			if format != "text" && format != "json" {
				return fmt.Errorf("unsupported format '%s': must be text or json", format)
			}

			ctx, cancel := cliContext()
			defer cancel()

			c, err := newCLIClient()
			if err != nil {
				return err
			}
			defer func() { _ = c.Close() }()

			ku, err := c.Propose(ctx, cq.ProposeParams{
				Summary:    summary,
				Detail:     detail,
				Action:     action,
				Domains:    domains,
				Languages:  languages,
				Frameworks: frameworks,
				Pattern:    pattern,
			})
			if err != nil {
				return err
			}

			if format == "json" {
				enc := json.NewEncoder(cmd.OutOrStdout())
				enc.SetIndent("", "  ")

				return enc.Encode(ku)
			}

			_, _ = fmt.Fprintf(cmd.OutOrStdout(), "Proposed: %s\n", ku.ID)

			return nil
		},
	}

	cmd.Flags().StringVar(&summary, "summary", "", "Brief summary of the insight (required)")
	cmd.Flags().StringVar(&detail, "detail", "", "Detailed explanation (required)")
	cmd.Flags().StringVar(&action, "action", "", "Recommended action (required)")
	cmd.Flags().StringArrayVar(&domains, "domain", nil, "Domain tags (required, repeatable)")
	cmd.Flags().StringArrayVar(&languages, "language", nil, "Programming language context (repeatable)")
	cmd.Flags().StringArrayVar(&frameworks, "framework", nil, "Framework context (repeatable)")
	cmd.Flags().StringVar(&pattern, "pattern", "", "Pattern context")
	cmd.Flags().StringVar(&format, "format", "text", "Output format: text or json")
	_ = cmd.MarkFlagRequired("summary")
	_ = cmd.MarkFlagRequired("detail")
	_ = cmd.MarkFlagRequired("action")
	_ = cmd.MarkFlagRequired("domain")

	return cmd
}
