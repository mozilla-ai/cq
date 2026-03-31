package cmd

import (
	"bytes"
	"encoding/json"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

// testSetup configures env vars for an isolated test client.
func testSetup(t *testing.T) {
	t.Helper()
	dbPath := filepath.Join(t.TempDir(), "test.db")
	t.Setenv("CQ_LOCAL_DB_PATH", dbPath)
	t.Setenv("CQ_ADDR", "")
	t.Setenv("CQ_TEAM_ADDR", "")
	t.Setenv("CQ_API_KEY", "")
}

func TestQueryRepeatedDomainFlags(t *testing.T) {
	testSetup(t)

	// Propose a unit first so the query has something to find.
	propose := NewProposeCmd()
	propose.SetArgs([]string{
		"--summary", "test insight",
		"--detail", "test detail",
		"--action", "test action",
		"--domain", "api",
		"--domain", "payments",
	})
	require.NoError(t, propose.Execute())

	// Query with repeated --domain flags.
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

func TestConfirmLocalUnit(t *testing.T) {
	testSetup(t)

	// Propose first.
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

	// Extract ID from JSON output.
	require.Contains(t, proposeBuf.String(), `"id"`)

	// We need the ID; parse it.
	// The JSON format produces a full KU object.
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

func TestPromptReturnsContent(t *testing.T) {

	prompt := NewPromptCmd()
	var buf bytes.Buffer
	prompt.SetOut(&buf)
	prompt.SetArgs([]string{})
	require.NoError(t, prompt.Execute())
	require.NotEmpty(t, buf.String())
}

func TestQueryUnsupportedFormat(t *testing.T) {
	testSetup(t)

	query := NewQueryCmd()
	query.SetArgs([]string{"--domain", "api", "--format", "xml"})
	require.Error(t, query.Execute())
}
