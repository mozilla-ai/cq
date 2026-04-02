package cmd

import (
	"bytes"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestQueryRepeatedDomainFlags(t *testing.T) {
	testSetup(t)

	propose := NewProposeCmd()
	propose.SetArgs([]string{
		"--summary", "test insight",
		"--detail", "test detail",
		"--action", "test action",
		"--domain", "api",
		"--domain", "payments",
	})
	require.NoError(t, propose.Execute())

	query := NewQueryCmd()
	var buf bytes.Buffer
	query.SetOut(&buf)
	query.SetArgs([]string{
		"--domain", "api",
		"--domain", "payments",
		"--format", "text",
	})
	require.NoError(t, query.Execute())
	require.Contains(t, buf.String(), "test insight")
}

func TestQueryRepeatedLanguageFlags(t *testing.T) {
	testSetup(t)

	propose := NewProposeCmd()
	propose.SetArgs([]string{
		"--summary", "multi-lang",
		"--detail", "d",
		"--action", "a",
		"--domain", "api",
		"--language", "go",
	})
	require.NoError(t, propose.Execute())

	query := NewQueryCmd()
	var buf bytes.Buffer
	query.SetOut(&buf)
	query.SetArgs([]string{
		"--domain", "api",
		"--language", "go",
		"--language", "python",
		"--format", "text",
	})
	require.NoError(t, query.Execute())
	require.Contains(t, buf.String(), "multi-lang")
}

func TestQueryRepeatedFrameworkFlags(t *testing.T) {
	testSetup(t)

	propose := NewProposeCmd()
	propose.SetArgs([]string{
		"--summary", "multi-fw",
		"--detail", "d",
		"--action", "a",
		"--domain", "api",
		"--framework", "grpc",
	})
	require.NoError(t, propose.Execute())

	query := NewQueryCmd()
	var buf bytes.Buffer
	query.SetOut(&buf)
	query.SetArgs([]string{
		"--domain", "api",
		"--framework", "grpc",
		"--framework", "http",
		"--format", "text",
	})
	require.NoError(t, query.Execute())
	require.Contains(t, buf.String(), "multi-fw")
}

func TestQueryJSONFormat(t *testing.T) {
	testSetup(t)

	propose := NewProposeCmd()
	propose.SetArgs([]string{
		"--summary", "json test",
		"--detail", "d",
		"--action", "a",
		"--domain", "api",
	})
	require.NoError(t, propose.Execute())

	query := NewQueryCmd()
	var buf bytes.Buffer
	query.SetOut(&buf)
	query.SetArgs([]string{"--domain", "api", "--format", "json"})
	require.NoError(t, query.Execute())
	require.Contains(t, buf.String(), `"domains"`)
	require.Contains(t, buf.String(), `"json test"`)
}

func TestQueryNoResults(t *testing.T) {
	testSetup(t)

	query := NewQueryCmd()
	var buf bytes.Buffer
	query.SetOut(&buf)
	query.SetArgs([]string{"--domain", "nonexistent"})
	require.NoError(t, query.Execute())
	require.Contains(t, buf.String(), "No matching knowledge units found.")
}

func TestQueryUnsupportedFormat(t *testing.T) {
	testSetup(t)

	query := NewQueryCmd()
	query.SetArgs([]string{"--domain", "api", "--format", "xml"})
	require.Error(t, query.Execute())
}
