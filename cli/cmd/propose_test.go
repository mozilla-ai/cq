package cmd

import (
	"bytes"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestProposeRepeatedDomainFlags(t *testing.T) {
	testSetup(t)

	propose := NewProposeCmd()
	var buf bytes.Buffer
	propose.SetOut(&buf)
	propose.SetArgs([]string{
		"--summary", "multi-domain",
		"--detail", "d",
		"--action", "a",
		"--domain", "api",
		"--domain", "payments",
		"--format", "json",
	})
	require.NoError(t, propose.Execute())
	require.Contains(t, buf.String(), `"api"`)
	require.Contains(t, buf.String(), `"payments"`)
}

func TestProposeTextFormat(t *testing.T) {
	testSetup(t)

	propose := NewProposeCmd()
	var buf bytes.Buffer
	propose.SetOut(&buf)
	propose.SetArgs([]string{
		"--summary", "s",
		"--detail", "d",
		"--action", "a",
		"--domain", "test",
	})
	require.NoError(t, propose.Execute())
	require.Contains(t, buf.String(), "Proposed: ku_")
}

// When a remote is configured but unreachable, propose must still succeed
// (unit stored locally) and surface a warning on stderr.
func TestProposeRemoteUnreachableWarns(t *testing.T) {
	testSetup(t)
	setFlag(t, &flagAddr, "http://127.0.0.1:1")

	propose := NewProposeCmd()
	var out, errBuf bytes.Buffer
	propose.SetOut(&out)
	propose.SetErr(&errBuf)
	propose.SetArgs([]string{
		"--summary", "fallback",
		"--detail", "d",
		"--action", "a",
		"--domain", "test",
	})
	require.NoError(t, propose.Execute())
	require.Contains(t, out.String(), "Proposed: ku_")
	require.Contains(t, errBuf.String(), "warning:")
	require.Contains(t, errBuf.String(), "stored locally after remote failure")
}
