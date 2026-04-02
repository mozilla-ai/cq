package cmd

import (
	"bytes"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestStatusTextFormat(t *testing.T) {
	testSetup(t)

	status := NewStatusCmd()
	var buf bytes.Buffer
	status.SetOut(&buf)
	status.SetArgs([]string{})
	require.NoError(t, status.Execute())
	require.Contains(t, buf.String(), "Knowledge units:")
}

func TestStatusJSONFormat(t *testing.T) {
	testSetup(t)

	status := NewStatusCmd()
	var buf bytes.Buffer
	status.SetOut(&buf)
	status.SetArgs([]string{"--format", "json"})
	require.NoError(t, status.Execute())
	require.Contains(t, buf.String(), `"total_count"`)
}
