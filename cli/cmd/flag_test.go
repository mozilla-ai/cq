package cmd

import (
	"bytes"
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestFlagWithReason(t *testing.T) {
	testSetup(t)

	propose := NewProposeCmd()
	var proposeBuf bytes.Buffer
	propose.SetOut(&proposeBuf)
	propose.SetArgs([]string{
		"--summary", "flaggable",
		"--detail", "d",
		"--action", "a",
		"--domain", "test",
		"--format", "json",
	})
	require.NoError(t, propose.Execute())

	var ku map[string]any
	require.NoError(t, json.Unmarshal(proposeBuf.Bytes(), &ku))
	unitID := ku["id"].(string)

	flag := NewFlagCmd()
	var flagBuf bytes.Buffer
	flag.SetOut(&flagBuf)
	flag.SetArgs([]string{unitID, "--reason", "stale", "--detail", "outdated"})
	require.NoError(t, flag.Execute())
	require.Contains(t, flagBuf.String(), "Flagged")
	require.Contains(t, flagBuf.String(), "stale")
}

func TestFlagInvalidReason(t *testing.T) {
	testSetup(t)

	flag := NewFlagCmd()
	flag.SetArgs([]string{"ku_00000000000000000000000000000001", "--reason", "bogus"})
	require.Error(t, flag.Execute())
}
