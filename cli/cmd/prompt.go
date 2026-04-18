package cmd

import (
	"encoding/json"
	"fmt"
	"io"

	"github.com/spf13/cobra"

	"github.com/mozilla-ai/cq/sdk/go/prompts"
)

// promptSubCmd describes a prompt subcommand that emits a single prompt body.
type promptSubCmd struct {
	// use is the subcommand name (e.g. "skill").
	use string

	// short is the one-line command summary.
	short string

	// long is the multi-line command description.
	long string

	// jsonKey is the top-level key used when --format=json.
	jsonKey string

	// body returns the prompt text to emit.
	body func() string
}

// NewPromptCmd returns the prompt command with its subcommands.
func NewPromptCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "prompt",
		Short: "Print a canonical cq agent prompt.",
		Long: "Print one of the canonical cq agent prompts for injection into an " +
			"agent system prompt. Use this when integrating cq into agent " +
			"frameworks that do not have the cq plugin installed.",
	}

	cmd.AddCommand(newPromptReflectCmd())
	cmd.AddCommand(newPromptSkillCmd())

	return cmd
}

// newPromptReflectCmd prints the /cq:reflect slash-command prompt.
func newPromptReflectCmd() *cobra.Command {
	return newPromptSubCmd(promptSubCmd{
		use:   "reflect",
		short: "Print the /cq:reflect slash-command prompt.",
		long: "Print the /cq:reflect slash-command prompt, which guides an agent " +
			"through session reflection and candidate proposal.",
		jsonKey: "prompt",
		body:    prompts.Reflect,
	})
}

// newPromptSkillCmd prints the canonical skill prompt.
func newPromptSkillCmd() *cobra.Command {
	return newPromptSubCmd(promptSubCmd{
		use:   "skill",
		short: "Print the cq agent skill prompt.",
		long: "Print the full cq agent skill prompt, which describes how an " +
			"agent should interact with the knowledge commons.",
		jsonKey: "prompt",
		body:    prompts.Skill,
	})
}

// newPromptSubCmd builds a prompt subcommand that emits the given prompt body
// in either text or JSON format.
func newPromptSubCmd(spec promptSubCmd) *cobra.Command {
	var format string

	cmd := &cobra.Command{
		Use:   spec.use,
		Short: spec.short,
		Long:  spec.long,
		RunE: func(cmd *cobra.Command, _ []string) error {
			return writePrompt(cmd.OutOrStdout(), format, spec.jsonKey, spec.body())
		},
	}

	cmd.Flags().StringVar(&format, "format", "text", "Output format: text or json")

	return cmd
}

// writePrompt emits the prompt body as text or a JSON document keyed by jsonKey.
func writePrompt(w io.Writer, format, jsonKey, body string) error {
	switch format {
	case "text":
		_, err := fmt.Fprint(w, body)
		return err
	case "json":
		enc := json.NewEncoder(w)
		enc.SetIndent("", jsonIndent)

		return enc.Encode(map[string]string{jsonKey: body})
	default:
		return fmt.Errorf("unsupported format '%s': must be text or json", format)
	}
}
