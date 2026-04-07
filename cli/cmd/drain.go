package cmd

import (
	"encoding/json"
	"fmt"

	"github.com/spf13/cobra"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// NewDrainCmd returns the drain command.
func NewDrainCmd() *cobra.Command {
	var (
		dryRun bool
		format string
	)

	cmd := &cobra.Command{
		Use:   "drain",
		Short: "Push local knowledge units to the remote store.",
		Long: "Push all locally-stored knowledge units to the configured remote API. " +
			"Successfully pushed units are removed from local storage.",
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

			if !c.HasRemote() {
				return fmt.Errorf("no remote API configured (set %s or use --addr)", envVarAddr)
			}

			if dryRun {
				count, err := c.DrainableCount(ctx)
				if err != nil {
					return err
				}

				return outputDryRunResult(cmd, count, format)
			}

			result, err := c.Drain(ctx)
			if err != nil {
				return err
			}

			return outputDrainResult(cmd, result, format)
		},
	}

	cmd.Flags().BoolVar(
		&dryRun,
		"dry-run",
		false,
		"Show what would be pushed without pushing",
	)
	cmd.Flags().StringVar(
		&format,
		"format",
		"text",
		"Output format: text or json",
	)

	return cmd
}

// outputDrainResult formats and writes the drain result.
func outputDrainResult(cmd *cobra.Command, result cq.DrainResult, format string) error {
	switch format {
	case "json":
		enc := json.NewEncoder(cmd.OutOrStdout())
		enc.SetIndent("", jsonIndent)
		return enc.Encode(result)
	case "text":
		w := cmd.OutOrStdout()
		_, _ = fmt.Fprintf(w, "Pushed %d unit(s) to remote.\n", result.Pushed)

		for _, warn := range result.Warnings {
			_, _ = fmt.Fprintf(w, "  warning: %v\n", warn)
		}
	default:
		return fmt.Errorf("unsupported format '%s'", format)
	}

	return nil
}

// outputDryRunResult formats and writes the dry-run result.
func outputDryRunResult(cmd *cobra.Command, count int, format string) error {
	if format == "json" {
		enc := json.NewEncoder(cmd.OutOrStdout())
		enc.SetIndent("", jsonIndent)

		return enc.Encode(map[string]any{
			"dry_run": true,
			"pending": count,
		})
	}

	_, _ = fmt.Fprintf(cmd.OutOrStdout(), "Would push %d unit(s) to remote.\n", count)

	return nil
}
