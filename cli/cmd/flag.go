package cmd

import (
	"errors"
	"fmt"
	"strings"

	"github.com/spf13/cobra"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

var cliReasonValues = map[string]cq.FlagReason{
	"stale":     cq.Stale,
	"incorrect": cq.Incorrect,
	"duplicate": cq.Duplicate,
}

// NewFlagCmd returns the flag command.
func NewFlagCmd() *cobra.Command {
	var reason string
	var detail string
	var duplicateOf string

	cmd := &cobra.Command{
		Use:   "flag <unit_id>",
		Short: "Flag a knowledge unit as problematic, reducing its confidence.",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			flagReason, ok := cliReasonValues[strings.ToLower(reason)]
			if !ok {
				return fmt.Errorf("invalid reason %s: must be stale, incorrect, or duplicate", reason)
			}

			ctx, cancel := cliContext()
			defer cancel()

			c, err := newCLIClient()
			if err != nil {
				return err
			}
			defer func() { _ = c.Close() }()

			opts := make([]cq.FlagOption, 0, 2)
			if detail != "" {
				opts = append(opts, cq.WithDetail(detail))
			}
			if duplicateOf != "" {
				opts = append(opts, cq.WithDuplicateOf(duplicateOf))
			}

			flagged, err := c.Flag(ctx, cq.KnowledgeUnit{ID: args[0], Tier: cq.Local}, flagReason, opts...)
			if errors.Is(err, cq.ErrNotFound) {
				flagged, err = c.Flag(ctx, cq.KnowledgeUnit{ID: args[0], Tier: cq.Private}, flagReason, opts...)
			}

			if err != nil {
				return err
			}

			_, _ = fmt.Fprintf(
				cmd.OutOrStdout(),
				"Flagged %s as %s (confidence: %.0f%%)\n",
				flagged.ID,
				reason,
				flagged.Evidence.Confidence*100,
			)

			return nil
		},
	}

	cmd.Flags().StringVar(&reason, "reason", "", "Flag reason: stale, incorrect, or duplicate (required)")
	cmd.Flags().StringVar(&detail, "detail", "", "Optional detail for why the unit was flagged")
	cmd.Flags().StringVar(&duplicateOf, "duplicate-of", "", "Original unit ID when reason is duplicate")
	_ = cmd.MarkFlagRequired("reason")

	return cmd
}
