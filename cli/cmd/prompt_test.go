package cmd

import (
	"bytes"
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestPromptSkillText(t *testing.T) {
	cmd := NewPromptCmd()
	var buf bytes.Buffer
	cmd.SetOut(&buf)
	cmd.SetArgs([]string{"skill"})
	require.NoError(t, cmd.Execute())
	require.NotEmpty(t, buf.String())
	require.Contains(t, buf.String(), "name: cq")
}

func TestPromptReflectText(t *testing.T) {
	cmd := NewPromptCmd()
	var buf bytes.Buffer
	cmd.SetOut(&buf)
	cmd.SetArgs([]string{"reflect"})
	require.NoError(t, cmd.Execute())
	require.NotEmpty(t, buf.String())
	require.Contains(t, buf.String(), "name: cq:reflect")
}

func TestPromptSkillJSON(t *testing.T) {
	cmd := NewPromptCmd()
	var buf bytes.Buffer
	cmd.SetOut(&buf)
	cmd.SetArgs([]string{"skill", "--format", "json"})
	require.NoError(t, cmd.Execute())

	var payload map[string]string
	require.NoError(t, json.Unmarshal(buf.Bytes(), &payload))
	require.NotEmpty(t, payload["prompt"])
	require.Contains(t, payload["prompt"], "name: cq")
}

func TestPromptReflectJSON(t *testing.T) {
	cmd := NewPromptCmd()
	var buf bytes.Buffer
	cmd.SetOut(&buf)
	cmd.SetArgs([]string{"reflect", "--format", "json"})
	require.NoError(t, cmd.Execute())

	var payload map[string]string
	require.NoError(t, json.Unmarshal(buf.Bytes(), &payload))
	require.NotEmpty(t, payload["prompt"])
	require.Contains(t, payload["prompt"], "name: cq:reflect")
}

func TestPromptRejectsUnknownFormat(t *testing.T) {
	cmd := NewPromptCmd()
	var buf bytes.Buffer
	cmd.SetOut(&buf)
	cmd.SetErr(&buf)
	cmd.SetArgs([]string{"skill", "--format", "yaml"})
	err := cmd.Execute()
	require.Error(t, err)
	require.Contains(t, err.Error(), "unsupported format")
}

func TestPromptBareInvocationShowsHelp(t *testing.T) {
	cmd := NewPromptCmd()
	var buf bytes.Buffer
	cmd.SetOut(&buf)
	cmd.SetArgs([]string{})
	require.NoError(t, cmd.Execute())
	// Cobra prints usage/help for parent commands without a RunE.
	require.Contains(t, buf.String(), "skill")
	require.Contains(t, buf.String(), "reflect")
}
