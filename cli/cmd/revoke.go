package cmd

import (
	"errors"
	"fmt"
	"net/http"

	"github.com/spf13/cobra"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// NewRevokeCmd returns the revoke command.
func NewRevokeCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "revoke <unit_id>",
		Short: "Withdraw one of your own knowledge units from review or circulation.",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
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

			revoked, err := c.Revoke(ctx, cq.KnowledgeUnit{ID: args[0], Tier: cq.Local})
			local := err == nil
			if errors.Is(err, cq.ErrNotFound) {
				revoked, err = c.Revoke(ctx, cq.KnowledgeUnit{ID: args[0], Tier: cq.Private})
				local = false
			}

			if err != nil {
				var remoteErr *cq.RemoteError
				if errors.As(err, &remoteErr) && remoteErr.StatusCode == http.StatusNotFound {
					return fmt.Errorf(
						"knowledge unit %s could not be withdrawn: either you did not propose it, "+
							"or the configured knowledge store does not support withdrawing a unit",
						args[0],
					)
				}

				return err
			}

			// A local unit has no review state, so revoking deletes it. Say which
			// happened, because only one of the two can be undone.
			if local {
				_, _ = fmt.Fprintf(cmd.OutOrStdout(), "Revoked %s (removed from the local store)\n", revoked.ID)

				return nil
			}

			_, _ = fmt.Fprintf(cmd.OutOrStdout(), "Revoked %s (withdrawn from review)\n", revoked.ID)

			return nil
		},
	}
}
