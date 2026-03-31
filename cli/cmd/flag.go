package cmd

import (
	"errors"
	"fmt"
	"strings"

	"github.com/spf13/cobra"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// flagReason implements pflag.Value for validated flag reason input.
type flagReason struct {
	value cq.FlagReason
}

// NewFlagCmd returns the flag command.
func NewFlagCmd() *cobra.Command {
	var reason flagReason
	var detail string
	var duplicateOf string

	cmd := &cobra.Command{
		Use:   "flag <unit_id>",
		Short: "Flag a knowledge unit as problematic, reducing its confidence.",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
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

			flagged, err := c.Flag(ctx, cq.KnowledgeUnit{ID: args[0], Tier: cq.Local}, reason.value, opts...)
			if errors.Is(err, cq.ErrNotFound) {
				flagged, err = c.Flag(ctx, cq.KnowledgeUnit{ID: args[0], Tier: cq.Private}, reason.value, opts...)
			}

			if err != nil {
				return err
			}

			_, _ = fmt.Fprintf(
				cmd.OutOrStdout(),
				"Flagged %s as %s (confidence: %.0f%%)\n",
				flagged.ID,
				reason.value,
				flagged.Evidence.Confidence*100,
			)

			return nil
		},
	}

	cmd.Flags().Var(&reason, "reason", fmt.Sprintf("Flag reason (one of: %s)", cq.AllFlagReasons().String()))
	cmd.Flags().StringVar(&detail, "detail", "", "Optional detail for why the unit was flagged")
	cmd.Flags().StringVar(&duplicateOf, "duplicate-of", "", "Original unit ID when reason is duplicate")
	_ = cmd.MarkFlagRequired("reason")

	return cmd
}

// Set validates and assigns the flag reason from a string value.
func (f *flagReason) Set(v string) error {
	v = strings.ToLower(strings.TrimSpace(v))
	for _, r := range cq.AllFlagReasons() {
		if string(r) == v {
			f.value = r
			return nil
		}
	}
	return fmt.Errorf("invalid reason '%s', must be one of: %s", v, cq.AllFlagReasons().String())
}

// String returns the current flag reason value.
func (f *flagReason) String() string {
	return string(f.value)
}

// Type returns the pflag type name for help text.
func (f *flagReason) Type() string {
	return "reason"
}
