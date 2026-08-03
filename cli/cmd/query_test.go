package cmd

import (
	"bytes"
	"encoding/json"
	"net/http"
	"strconv"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	cq "github.com/mozilla-ai/cq/sdk/go"
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

func TestQueryPrintsRemoteWarningsToStderr(t *testing.T) {
	testSetup(t)

	// Fake remote that returns a bare JSON array instead of the {data: [...]}
	// envelope. The SDK should fail to decode and surface a warning, which
	// the CLI must print to stderr.
	withFakeRemote(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte("[]"))
	}))

	query := NewQueryCmd()
	var out, errBuf bytes.Buffer
	query.SetOut(&out)
	query.SetErr(&errBuf)
	query.SetArgs([]string{"--domain", "api"})
	require.NoError(t, query.Execute())

	// The warning must be specifically about the decode failure; a generic
	// "warning:" line could come from any future warning source and would
	// mask a regression where the decode error stops surfacing.
	stderr := errBuf.String()
	require.Contains(t, stderr, "warning:")
	require.Contains(t, stderr, "decoding")
}

func TestQueryHonorsConfiguredRemoteTimeout(t *testing.T) {
	testSetup(t)

	// The remote responds slower than the SDK's default HTTP timeout but faster
	// than the configured CQ_TIMEOUT, so the request only succeeds if CQ_TIMEOUT
	// is what governs the client. Guard the ordering so a future bump to the SDK
	// default fails loudly here instead of flaking.
	const configuredTimeout = 8 * time.Second
	remoteDelay := cq.DefaultTimeout() + time.Second
	require.Less(t, remoteDelay, configuredTimeout,
		"SDK default HTTP timeout grew too close to CQ_TIMEOUT; raise configuredTimeout")

	t.Setenv(envVarTimeout, strconv.Itoa(int(configuredTimeout/time.Second)))
	withFakeRemote(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/knowledge" {
			http.NotFound(w, r)
			return
		}

		time.Sleep(remoteDelay)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(
			[]byte(
				`{"data":[{"id":"ku_00000000000000000000000000000001","version":1,"domains":["api"],"insight":{"summary":"slow remote response","detail":"d","action":"a"},"context":{"languages":[],"frameworks":[],"pattern":""},"evidence":{"confidence":0.5,"confirmations":1},"tier":"private","flags":[]}]}`,
			),
		)
	}))

	query := NewQueryCmd()
	var out bytes.Buffer
	query.SetOut(&out)
	query.SetArgs([]string{"--domain", "api"})
	require.NoError(t, query.Execute())
	require.Contains(t, out.String(), "slow remote response")
}

func TestQueryPatternFlag(t *testing.T) {
	testSetup(t)

	// Seed two KUs on the same domain so domain match alone cannot decide ranking.
	// Only one carries the pattern; the other is a plain domain match.
	// The plain KU is inserted first so a "pattern flag is silently dropped" regression
	// would leave it ranked first by insertion order, distinguishing it from the correct
	// behavior where the pattern boost lifts the matching KU above the plain one.
	proposePlain := NewProposeCmd()
	proposePlain.SetArgs([]string{
		"--summary", "plain insight",
		"--detail", "d",
		"--action", "a",
		"--domain", "api",
	})
	require.NoError(t, proposePlain.Execute())

	proposeMatch := NewProposeCmd()
	proposeMatch.SetArgs([]string{
		"--summary", "pattern insight",
		"--detail", "d",
		"--action", "a",
		"--domain", "api",
		"--pattern", "api-client",
	})
	require.NoError(t, proposeMatch.Execute())

	// Use JSON output so the ranking order is observable as an array index.
	query := NewQueryCmd()
	var buf bytes.Buffer
	query.SetOut(&buf)
	query.SetArgs([]string{
		"--domain", "api",
		"--pattern", "api-client",
		"--format", "json",
	})
	require.NoError(t, query.Execute())

	var units []cq.KnowledgeUnit
	require.NoError(t, json.Unmarshal(buf.Bytes(), &units))
	require.Len(t, units, 2)
	require.Equal(t, "pattern insight", units[0].Insight.Summary,
		"the unit with matching pattern should rank first when --pattern is threaded into QueryParams")
}
