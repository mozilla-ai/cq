package cmd

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestHookCmdRoutesStopOutput(t *testing.T) {
	dir := t.TempDir()
	// Seed a failure via the command itself.
	failCmd := NewHookCmd()
	failCmd.SetIn(bytes.NewBufferString(
		`{"conversation_id":"c1","tool_name":"Bash","tool_input":{"command":"go build"},"error_message":"boom"}`))
	failCmd.SetArgs([]string{"--host", "cursor", "--mode", "post-tool-use-failure", "--state-dir", dir})
	require.NoError(t, failCmd.Execute())
	require.FileExists(t, filepath.Join(dir, "c1-failure.json"))

	var out bytes.Buffer
	stopCmd := NewHookCmd()
	stopCmd.SetIn(bytes.NewBufferString(`{"conversation_id":"c1","status":"completed"}`))
	stopCmd.SetOut(&out)
	stopCmd.SetArgs([]string{"--host", "cursor", "--mode", "stop", "--state-dir", dir})
	require.NoError(t, stopCmd.Execute())
	require.Contains(t, out.String(), "previous tool Bash failed: boom")
}

func TestHookCmdRequiresFlags(t *testing.T) {
	cmd := NewHookCmd()
	cmd.SetArgs([]string{"--host", "cursor", "--mode", "stop"})
	require.Error(t, cmd.Execute())
}

func TestHookCmdIsHidden(t *testing.T) {
	require.True(t, NewHookCmd().Hidden)
}

func TestHookCmdSwallowsInternalErrors(t *testing.T) {
	dir := t.TempDir()
	// Point --state-dir at a file, not a directory, so MkdirAll fails.
	statePath := filepath.Join(dir, "not-a-dir")
	require.NoError(t, os.WriteFile(statePath, []byte("x"), 0o644))

	cmd := NewHookCmd()
	cmd.SetIn(bytes.NewBufferString(`{}`))
	cmd.SetArgs([]string{"--host", "cursor", "--mode", "stop", "--state-dir", statePath})
	require.NoError(t, cmd.Execute())
}
