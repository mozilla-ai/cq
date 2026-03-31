package cmd

import (
	"encoding/json"
	"fmt"
	"sort"

	"github.com/spf13/cobra"
)

// NewStatusCmd returns the status command.
func NewStatusCmd() *cobra.Command {
	var format string

	cmd := &cobra.Command{
		Use:   "status",
		Short: "Show knowledge store status.",
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

			stats, err := c.Status(ctx)
			if err != nil {
				return err
			}

			if format == "json" {
				enc := json.NewEncoder(cmd.OutOrStdout())
				enc.SetIndent("", "  ")

				return enc.Encode(stats)
			}

			w := cmd.OutOrStdout()
			_, _ = fmt.Fprintf(w, "Knowledge units: %d\n\n", stats.TotalCount)

			if len(stats.DomainCounts) > 0 {
				_, _ = fmt.Fprintln(w, "Domains:")

				domains := make([]string, 0, len(stats.DomainCounts))
				for d := range stats.DomainCounts {
					domains = append(domains, d)
				}

				sort.Strings(domains)
				for _, d := range domains {
					_, _ = fmt.Fprintf(w, "  %-20s %d\n", d, stats.DomainCounts[d])
				}

				_, _ = fmt.Fprintln(w)
			}

			if len(stats.Recent) > 0 {
				_, _ = fmt.Fprintln(w, "Recent:")
				for _, ku := range stats.Recent {
					_, _ = fmt.Fprintf(w, "  [%s] %s\n", ku.ID, ku.Insight.Summary)
				}

				_, _ = fmt.Fprintln(w)
			}

			if len(stats.ConfidenceDistribution) > 0 {
				_, _ = fmt.Fprintln(w, "Confidence distribution:")
				for _, b := range []string{"[0.0-0.3)", "[0.3-0.5)", "[0.5-0.7)", "[0.7-1.0]"} {
					_, _ = fmt.Fprintf(w, "  %-10s %d\n", b, stats.ConfidenceDistribution[b])
				}
			}

			return nil
		},
	}

	cmd.Flags().StringVar(&format, "format", "text", "Output format: text or json")

	return cmd
}
