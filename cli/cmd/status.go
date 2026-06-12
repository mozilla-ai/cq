package cmd

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"

	"github.com/spf13/cobra"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// maxDisplayDomains caps how many domains the text view lists inline before
// truncating the remainder.
const maxDisplayDomains = 8

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

			for _, w := range stats.Warnings {
				_, _ = fmt.Fprintf(cmd.ErrOrStderr(), "warning: %s\n", w)
			}

			if format == "json" {
				enc := json.NewEncoder(cmd.OutOrStdout())
				enc.SetIndent("", jsonIndent)

				return enc.Encode(stats)
			}

			w := cmd.OutOrStdout()
			_, _ = fmt.Fprintf(w, "Knowledge units: %d\n\n", stats.TotalCount)

			// Render the per-tier split whenever any tier holds units, in
			// canonical order, omitting empty tiers. Collecting the lines
			// first avoids emitting a bare "By tier:" header for an empty
			// store.
			var tierLines []string
			for _, tier := range []cq.Tier{cq.Local, cq.Private, cq.Public} {
				if count := stats.TierCounts[tier]; count > 0 {
					tierLines = append(tierLines, fmt.Sprintf("  %-20s %d", tier, count))
				}
			}

			if len(tierLines) > 0 {
				_, _ = fmt.Fprintln(w, "By tier:")
				for _, line := range tierLines {
					_, _ = fmt.Fprintln(w, line)
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
				_, _ = fmt.Fprintln(w, "Confidence distribution (excludes public commons):")
				for _, b := range cq.ConfidenceBucketLabels() {
					_, _ = fmt.Fprintf(w, "  %-10s %d\n", b, stats.ConfidenceDistribution[b])
				}
			}

			// Domains are the least important section, so they sit last and
			// stay compact: a count, then the most-tagged few inline with the
			// remainder truncated.
			if len(stats.DomainCounts) > 0 {
				domains := make([]string, 0, len(stats.DomainCounts))
				for d := range stats.DomainCounts {
					domains = append(domains, d)
				}
				// Most-tagged first; ties broken alphabetically.
				sort.Slice(domains, func(i, j int) bool {
					if ci, cj := stats.DomainCounts[domains[i]], stats.DomainCounts[domains[j]]; ci != cj {
						return ci > cj
					}

					return domains[i] < domains[j]
				})

				shown := domains
				if len(shown) > maxDisplayDomains {
					shown = shown[:maxDisplayDomains]
				}

				parts := make([]string, len(shown))
				for i, d := range shown {
					parts[i] = fmt.Sprintf("%s (%d)", d, stats.DomainCounts[d])
				}

				line := strings.Join(parts, ", ")
				if remaining := len(domains) - len(shown); remaining > 0 {
					line += fmt.Sprintf(" ... +%d more", remaining)
				}

				_, _ = fmt.Fprintln(w)
				_, _ = fmt.Fprintf(w, "Domains: %d total\n", len(stats.DomainCounts))
				_, _ = fmt.Fprintf(w, "  %s\n", line)
			}

			return nil
		},
	}

	cmd.Flags().StringVar(&format, "format", "text", "Output format: text or json")

	return cmd
}
