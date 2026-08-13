package cmd

import (
	"bytes"
	"fmt"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"

	cqschema "github.com/mozilla-ai/cq/schema"
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

// Free-text over the schema ceiling is rejected at the CLI with a clean
// validation error naming the field and its limit (sourced from the schema),
// and nothing is proposed. The CLI relies on the SDK's enforcement and renders
// the resulting error rather than truncating or passing it downstream.
func TestProposeRejectsOverLimitField(t *testing.T) {
	testSetup(t)

	over := cqschema.SummaryMaxLength() + 1
	propose := NewProposeCmd()
	var out, errBuf bytes.Buffer
	propose.SetOut(&out)
	propose.SetErr(&errBuf)
	propose.SetArgs([]string{
		"--summary", strings.Repeat("x", over),
		"--detail", "d",
		"--action", "a",
		"--domain", "test",
	})

	want := fmt.Sprintf("summary must be at most %d characters, got %d", cqschema.SummaryMaxLength(), over)
	require.EqualError(t, propose.Execute(), want)
	require.NotContains(t, out.String(), "Proposed:")
}

// A configured-but-unreachable remote must not mask an over-limit rejection:
// validation runs before the fallback path, so the CLI surfaces the validation
// error rather than reporting a local-store success.
func TestProposeRejectsOverLimitBeforeRemoteFallback(t *testing.T) {
	testSetup(t)
	setFlag(t, &flagAddr, "http://127.0.0.1:1")

	over := cqschema.SummaryMaxLength() + 1
	propose := NewProposeCmd()
	var out, errBuf bytes.Buffer
	propose.SetOut(&out)
	propose.SetErr(&errBuf)
	propose.SetArgs([]string{
		"--summary", strings.Repeat("x", over),
		"--detail", "d",
		"--action", "a",
		"--domain", "test",
	})

	want := fmt.Sprintf("summary must be at most %d characters, got %d", cqschema.SummaryMaxLength(), over)
	require.EqualError(t, propose.Execute(), want)
	require.NotContains(t, out.String(), "Proposed:")
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
