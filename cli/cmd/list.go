package cmd

import (
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"text/tabwriter"

	"github.com/spf13/cobra"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

const (
	// defaultListLimit is the page size the list command requests.
	defaultListLimit = 20

	// listColumnPadding is the number of spaces between output columns.
	listColumnPadding = 2
)

// reviewStatus implements pflag.Value for validated review status input.
type reviewStatus struct {
	value cq.ReviewStatus
}

// NewListCmd returns the list command.
func NewListCmd() *cobra.Command {
	var (
		cursor     string
		domains    []string
		format     string
		frameworks []string
		languages  []string
		limit      int
		pattern    string
		search     string
		status     reviewStatus
	)

	cmd := &cobra.Command{
		Use:   "list",
		Short: "List your own knowledge units and their review state.",
		RunE: func(cmd *cobra.Command, _ []string) error {
			if format != "text" && format != "json" {
				return fmt.Errorf("unsupported format '%s': must be text or json", format)
			}

			ctx, cancel, err := cliContext()
			if err != nil {
				return err
			}
			defer cancel()

			c, err := newCLIClient()
			if err != nil {
				return err
			}
			defer func() { _ = c.Close() }()

			params := cq.ListParams{
				Cursor:     cursor,
				Domains:    domains,
				Frameworks: frameworks,
				Languages:  languages,
				Limit:      limit,
				Pattern:    pattern,
				Search:     search,
				Status:     status.value,
			}

			result, err := c.List(ctx, params)
			if err != nil {
				return err
			}

			for _, w := range result.Warnings {
				_, _ = fmt.Fprintf(cmd.ErrOrStderr(), "warning: %s\n", w)
			}

			if format == "json" {
				enc := json.NewEncoder(cmd.OutOrStdout())
				enc.SetIndent("", jsonIndent)

				return enc.Encode(result)
			}

			return writeListText(cmd.OutOrStdout(), result)
		},
	}

	cmd.Flags().StringVar(
		&cursor,
		"cursor",
		"",
		"Resume the listing from a previous page's cursor",
	)
	cmd.Flags().StringArrayVar(
		&domains,
		"domain",
		nil,
		"Filter by domain tag (repeatable)",
	)
	cmd.Flags().StringVar(
		&format,
		"format",
		"text",
		"Output format: text or json",
	)
	cmd.Flags().StringArrayVar(
		&frameworks,
		"framework",
		nil,
		"Filter by framework (repeatable)",
	)
	cmd.Flags().StringArrayVar(
		&languages,
		"language",
		nil,
		"Filter by programming language (repeatable)",
	)
	cmd.Flags().IntVar(
		&limit,
		"limit",
		defaultListLimit,
		"Maximum units per page",
	)
	cmd.Flags().StringVar(
		&pattern,
		"pattern",
		"",
		"Filter by pattern",
	)
	cmd.Flags().StringVar(
		&search,
		"search",
		"",
		"Filter by text in the summary, detail or action",
	)
	cmd.Flags().Var(
		&status,
		"status",
		fmt.Sprintf("Filter by review status (one of: %s)", cq.AllReviewStatuses().String()),
	)

	return cmd
}

// Set validates and assigns the review status from a string value.
func (s *reviewStatus) Set(v string) error {
	v = strings.ToLower(strings.TrimSpace(v))

	status := cq.ReviewStatus(v)
	if !status.Valid() {
		return fmt.Errorf("invalid status '%s', must be one of: %s", v, cq.AllReviewStatuses().String())
	}

	s.value = status

	return nil
}

// String returns the current review status value.
func (s *reviewStatus) String() string {
	return string(s.value)
}

// Type returns the pflag type name for help text.
func (s *reviewStatus) Type() string {
	return "status"
}

// writeListText renders a listing as one column-aligned line per unit. Facets
// are omitted; they are reported by the JSON format only.
func writeListText(out io.Writer, result cq.ListResult) error {
	if len(result.Units) == 0 {
		_, err := fmt.Fprintln(out, "No knowledge units found.")

		return err
	}

	tw := tabwriter.NewWriter(out, 0, 0, listColumnPadding, ' ', 0)
	_, _ = fmt.Fprintln(tw, "ID\tSTATUS\tCONF\tSUMMARY")

	for _, unit := range result.Units {
		_, _ = fmt.Fprintf(
			tw,
			"%s\t%s\t%.0f%%\t%s\n",
			unit.ID,
			unit.Status,
			unit.Evidence.Confidence*100,
			unit.Insight.Summary,
		)
	}

	if err := tw.Flush(); err != nil {
		return fmt.Errorf("writing listing: %w", err)
	}

	noun := "units"
	if len(result.Units) == 1 {
		noun = "unit"
	}

	_, _ = fmt.Fprintf(out, "\nShowing %d %s.", len(result.Units), noun)

	if result.NextCursor != "" {
		_, _ = fmt.Fprintf(out, " Next page: --cursor %s", result.NextCursor)
	}

	_, err := fmt.Fprintln(out)

	return err
}
