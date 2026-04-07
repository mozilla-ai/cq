package cmd

import (
	"bytes"
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestConfirmLocalUnit(t *testing.T) {
	testSetup(t)

	propose := NewProposeCmd()
	var proposeBuf bytes.Buffer
	propose.SetOut(&proposeBuf)
	propose.SetArgs([]string{
		"--summary", "confirmable",
		"--detail", "d",
		"--action", "a",
		"--domain", "test",
		"--format", "json",
	})
	require.NoError(t, propose.Execute())

	require.Contains(t, proposeBuf.String(), `"id"`)

	var ku map[string]any
	require.NoError(t, json.Unmarshal(proposeBuf.Bytes(), &ku))
	unitID := ku["id"].(string)

	confirm := NewConfirmCmd()
	var confirmBuf bytes.Buffer
	confirm.SetOut(&confirmBuf)
	confirm.SetArgs([]string{unitID})
	require.NoError(t, confirm.Execute())
	require.Contains(t, confirmBuf.String(), "Confirmed")
	require.Contains(t, confirmBuf.String(), unitID)
}
