package cmd

import (
	"errors"
	"fmt"

	"github.com/spf13/cobra"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// NewConfirmCmd returns the confirm command.
func NewConfirmCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "confirm <unit_id>",
		Short: "Confirm a knowledge unit proved correct, boosting its confidence.",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			ctx, cancel := cliContext()
			defer cancel()

			c, err := newCLIClient()
			if err != nil {
				return err
			}
			defer func() { _ = c.Close() }()

			confirmed, err := c.Confirm(ctx, cq.KnowledgeUnit{ID: args[0], Tier: cq.Local})
			if errors.Is(err, cq.ErrNotFound) {
				confirmed, err = c.Confirm(ctx, cq.KnowledgeUnit{ID: args[0], Tier: cq.Private})
			}

			if err != nil {
				return err
			}

			_, _ = fmt.Fprintf(
				cmd.OutOrStdout(),
				"Confirmed %s (confidence: %.0f%%)\n",
				confirmed.ID,
				confirmed.Evidence.Confidence*100,
			)

			return nil
		},
	}
}
