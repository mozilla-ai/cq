package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

// NewApproveCmd returns the approve command.
func NewApproveCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "approve <unit_id>",
		Short: "Approve a pending knowledge unit in the review queue.",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			ctx, cancel := cliContext()
			defer cancel()

			c, err := newCLIClient()
			if err != nil {
				return err
			}
			defer func() { _ = c.Close() }()

			result, err := c.Approve(ctx, args[0])
			if err != nil {
				return err
			}

			_, _ = fmt.Fprintf(
				cmd.OutOrStdout(),
				"Approved %s (status: %s, reviewed by: %s, reviewed at: %s)\n",
				result.UnitID,
				result.Status,
				result.ReviewedBy,
				result.ReviewedAt,
			)

			return nil
		},
	}
}
