package install

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestPosixJoin(t *testing.T) {
	require.Equal(t, "cq _hook --mode stop", posixJoin([]string{"cq", "_hook", "--mode", "stop"}))
	require.Equal(t,
		`/path/to/cq _hook --state-dir '/Users/Ada Lovelace/.cursor/cq-hook-state'`,
		posixJoin([]string{"/path/to/cq", "_hook", "--state-dir", "/Users/Ada Lovelace/.cursor/cq-hook-state"}))
	// Embedded single quote is escaped as '\''.
	require.Equal(t, `'a'\''b'`, posixJoin([]string{"a'b"}))
	require.Equal(t, "''", posixJoin([]string{""}))
}

func TestShellJoinDispatchesToPlatform(t *testing.T) {
	// shellJoin dispatches to posixJoin or windowsJoin based on the host OS;
	// confirm it at least produces the unquoted form for simple safe args.
	result := shellJoin("cq", "_hook", "--mode", "stop")
	require.Equal(t, "cq _hook --mode stop", result)
}

func TestWindowsJoin(t *testing.T) {
	require.Equal(t, "cq _hook --mode stop", windowsJoin([]string{"cq", "_hook", "--mode", "stop"}))
	require.Equal(t,
		`C:\cq _hook --state-dir "C:\Users\Ada Lovelace\.cursor\cq-hook-state"`,
		windowsJoin([]string{`C:\cq`, "_hook", "--state-dir", `C:\Users\Ada Lovelace\.cursor\cq-hook-state`}))
	// A trailing backslash before the closing quote is doubled.
	require.Equal(t, `"C:\dir with space\\"`, windowsJoin([]string{`C:\dir with space\`}))
}
