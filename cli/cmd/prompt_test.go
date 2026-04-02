package cmd

import (
	"bytes"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestPromptReturnsContent(t *testing.T) {
	prompt := NewPromptCmd()
	var buf bytes.Buffer
	prompt.SetOut(&buf)
	prompt.SetArgs([]string{})
	require.NoError(t, prompt.Execute())
	require.NotEmpty(t, buf.String())
}
