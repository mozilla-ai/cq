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
