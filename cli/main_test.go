package main

import (
	"fmt"
	"os"
	"os/exec"
	"testing"

	"github.com/stretchr/testify/require"
)

// helpSubprocessEnv triggers the in-process help rendering used by
// TestPromptHelpDoesNotRecurse when set on the re-executed test binary.
const helpSubprocessEnv = "CQ_HELP_SUBPROCESS_ARGS"

// TestPromptHelpDoesNotRecurse guards against the help-func recursion that
// caused `cq prompt <sub> --help` to stack overflow.
//
// The crash is a fatal runtime error that recover cannot catch, so each case
// renders help in a re-executed subprocess: a regression aborts that child
// with a non-zero exit instead of taking down the whole test process.
func TestPromptHelpDoesNotRecurse(t *testing.T) {
	if args := os.Getenv(helpSubprocessEnv); args != "" {
		rootCmd := newRootCmd()
		rootCmd.SetArgs([]string{"prompt", args, "--help"})

		// Exit non-zero on any render error so the parent's exit-status check
		// catches it, not only the fatal stack overflow this test guards.
		if err := rootCmd.Execute(); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}

		return
	}

	for _, sub := range []string{"skill", "reflect"} {
		t.Run(sub, func(t *testing.T) {
			cmd := exec.Command(os.Args[0], "-test.run=^TestPromptHelpDoesNotRecurse$")
			cmd.Env = append(os.Environ(), helpSubprocessEnv+"="+sub)

			out, err := cmd.CombinedOutput()
			require.NoErrorf(t, err, "rendering `prompt %s --help` crashed:\n%s", sub, out)
			require.Contains(t, string(out), "cq prompt "+sub)
		})
	}
}
