package cmd

import (
	"encoding/json"
	"fmt"

	"github.com/spf13/cobra"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// NewQueryCmd returns the query command.
func NewQueryCmd() *cobra.Command {
	var (
		domains   []string
		language  string
		framework string
		limit     int
		format    string
	)

	cmd := &cobra.Command{
		Use:   "query",
		Short: "Search for relevant knowledge units by domain tags.",
		RunE: func(cmd *cobra.Command, _ []string) error {
			if format != "text" && format != "json" {
				return fmt.Errorf("unsupported format %s: must be text or json", format)
			}

			ctx, cancel := cliContext()
			defer cancel()

			c, err := newCLIClient()
			if err != nil {
				return err
			}
			defer func() { _ = c.Close() }()

			qr, err := c.Query(ctx, cq.QueryParams{
				Domains:   domains,
				Language:  language,
				Framework: framework,
				Limit:     limit,
			})
			if err != nil {
				return err
			}

			if format == "json" {
				enc := json.NewEncoder(cmd.OutOrStdout())
				enc.SetIndent("", "  ")

				return enc.Encode(qr.Units)
			}

			if len(qr.Units) == 0 {
				_, _ = fmt.Fprintln(cmd.OutOrStdout(), "No matching knowledge units found.")

				return nil
			}

			for _, ku := range qr.Units {
				_, _ = fmt.Fprintf(cmd.OutOrStdout(), "[%s] (%.0f%%) %s\n",
					ku.ID, ku.Evidence.Confidence*100, ku.Insight.Summary)
				_, _ = fmt.Fprintf(cmd.OutOrStdout(), "  %s\n", ku.Insight.Detail)
				_, _ = fmt.Fprintf(cmd.OutOrStdout(), "  Action: %s\n\n", ku.Insight.Action)
			}

			return nil
		},
	}

	cmd.Flags().StringSliceVar(&domains, "domain", nil, "Domain tags to search (required, repeatable)")
	cmd.Flags().StringVar(&language, "language", "", "Filter by programming language")
	cmd.Flags().StringVar(&framework, "framework", "", "Filter by framework")
	cmd.Flags().IntVar(&limit, "limit", 5, "Maximum results")
	cmd.Flags().StringVar(&format, "format", "text", "Output format: text or json")
	_ = cmd.MarkFlagRequired("domain")

	return cmd
}
