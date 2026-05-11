package auth

import (
	"bufio"
	"fmt"
	"io"
	"strings"
)

// onboardingPrompt is the text shown before each username read.
const onboardingPrompt = "Username: "

// readUsername prompts the user and reads the next non-empty line.
// EOF before any input is treated as cancellation. Empty lines
// re-prompt without involving the server.
func readUsername(scanner *bufio.Scanner, out io.Writer) (string, error) {
	for {
		_, _ = fmt.Fprint(out, onboardingPrompt)

		if !scanner.Scan() {
			if err := scanner.Err(); err != nil {
				return "", fmt.Errorf("reading username: %w", err)
			}

			return "", io.EOF
		}

		username := strings.TrimSpace(scanner.Text())
		if username != "" {
			return username, nil
		}

		_, _ = fmt.Fprintln(out, "Username cannot be empty.")
	}
}

// renderInvalidFormat writes the platform's format-validation feedback
// to out.
func renderInvalidFormat(out io.Writer, username, detail string) {
	if detail == "" {
		_, _ = fmt.Fprintf(out, "Username '%s' is not in a valid format.\n", username)

		return
	}

	_, _ = fmt.Fprintf(out, "Username '%s' is not in a valid format: %s\n", username, detail)
}

// renderUnavailable writes a "username taken" message with optional
// suggestions to out.
func renderUnavailable(out io.Writer, username string, suggestions []string) {
	_, _ = fmt.Fprintf(out, "Username '%s' is unavailable.\n", username)

	if len(suggestions) > 0 {
		_, _ = fmt.Fprintf(out, "Suggestions: %s\n", strings.Join(suggestions, ", "))
	}
}
