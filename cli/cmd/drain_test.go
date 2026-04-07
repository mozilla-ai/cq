package cmd

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestDrainNoRemote(t *testing.T) {
	testSetup(t)

	drain := NewDrainCmd()
	require.Error(t, drain.Execute())
}

func TestDrainDryRunTextFormat(t *testing.T) {
	testSetup(t)
	setFlag(t, &flagAddr, "http://127.0.0.1:1")

	propose := NewProposeCmd()
	propose.SetArgs([]string{
		"--summary", "drainable",
		"--detail", "d",
		"--action", "a",
		"--domain", "test",
	})
	require.NoError(t, propose.Execute())

	drain := NewDrainCmd()
	var buf bytes.Buffer
	drain.SetOut(&buf)
	drain.SetArgs([]string{"--dry-run"})
	require.NoError(t, drain.Execute())
	require.Contains(t, buf.String(), "Would push 1 unit(s) to remote.")
}

func TestDrainDryRunJSONFormat(t *testing.T) {
	testSetup(t)
	setFlag(t, &flagAddr, "http://127.0.0.1:1")

	propose := NewProposeCmd()
	propose.SetArgs([]string{
		"--summary", "drainable",
		"--detail", "d",
		"--action", "a",
		"--domain", "test",
	})
	require.NoError(t, propose.Execute())

	drain := NewDrainCmd()
	var buf bytes.Buffer
	drain.SetOut(&buf)
	drain.SetArgs([]string{"--dry-run", "--format", "json"})
	require.NoError(t, drain.Execute())
	require.Contains(t, buf.String(), `"dry_run"`)
	require.Contains(t, buf.String(), `"pending"`)
}

func TestDrainPushesUnits(t *testing.T) {
	testSetup(t)

	var pushCount int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/propose" && r.Method == "POST" {
			pushCount++
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusCreated)
			_, _ = w.Write([]byte(`{"id":"ku_00000000000000000000000000000001","version":1,"domains":["test"],"insight":{"summary":"s","detail":"d","action":"a"},"context":{"languages":[],"frameworks":[],"pattern":""},"evidence":{"confidence":0.5,"confirmations":1},"tier":"local","flags":[]}`))

			return
		}

		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	// Propose locally first (no remote configured).
	propose := NewProposeCmd()
	propose.SetArgs([]string{
		"--summary", "push-me",
		"--detail", "d",
		"--action", "a",
		"--domain", "test",
	})
	require.NoError(t, propose.Execute())

	// Point at remote, then drain.
	setFlag(t, &flagAddr, srv.URL)

	drain := NewDrainCmd()
	var buf bytes.Buffer
	drain.SetOut(&buf)
	require.NoError(t, drain.Execute())
	require.Equal(t, 1, pushCount)
	require.Contains(t, buf.String(), "Pushed 1 unit(s) to remote.")
}

func TestDrainJSONFormat(t *testing.T) {
	testSetup(t)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/propose" && r.Method == "POST" {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusCreated)
			_, _ = w.Write([]byte(`{"id":"ku_00000000000000000000000000000001","version":1,"domains":["test"],"insight":{"summary":"s","detail":"d","action":"a"},"context":{"languages":[],"frameworks":[],"pattern":""},"evidence":{"confidence":0.5,"confirmations":1},"tier":"local","flags":[]}`))

			return
		}

		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	// Propose locally first (no remote configured).
	propose := NewProposeCmd()
	propose.SetArgs([]string{
		"--summary", "push-me",
		"--detail", "d",
		"--action", "a",
		"--domain", "test",
	})
	require.NoError(t, propose.Execute())

	// Point at remote, then drain.
	setFlag(t, &flagAddr, srv.URL)

	drain := NewDrainCmd()
	var buf bytes.Buffer
	drain.SetOut(&buf)
	drain.SetArgs([]string{"--format", "json"})
	require.NoError(t, drain.Execute())
	require.Contains(t, buf.String(), `"pushed"`)
}

func TestDrainUnsupportedFormat(t *testing.T) {
	testSetup(t)
	setFlag(t, &flagAddr, "http://127.0.0.1:1")

	drain := NewDrainCmd()
	drain.SetArgs([]string{"--format", "xml"})
	require.Error(t, drain.Execute())
}

func TestDrainAddrFromEnv(t *testing.T) {
	testSetup(t)

	// Simulate InitFlags having resolved the env var into flagAddr.
	t.Setenv(envVarAddr, "http://env-addr:8742")
	setFlag(t, &flagAddr, "http://env-addr:8742")

	// Client should be created with the env-derived addr.
	c, err := newCLIClient()
	require.NoError(t, err)
	defer func() { _ = c.Close() }()
	require.True(t, c.HasRemote())
}

func TestDrainAddrFlagOverridesEnv(t *testing.T) {
	testSetup(t)

	var pushCount int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/propose" && r.Method == "POST" {
			pushCount++
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusCreated)
			_, _ = w.Write([]byte(`{"id":"ku_00000000000000000000000000000001","version":1,"domains":["test"],"insight":{"summary":"s","detail":"d","action":"a"},"context":{"languages":[],"frameworks":[],"pattern":""},"evidence":{"confidence":0.5,"confirmations":1},"tier":"local","flags":[]}`))

			return
		}

		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	// Propose locally first (no remote configured).
	propose := NewProposeCmd()
	propose.SetArgs([]string{
		"--summary", "push-me",
		"--detail", "d",
		"--action", "a",
		"--domain", "test",
	})
	require.NoError(t, propose.Execute())

	// Env says one thing, but the flag (simulating --addr) says another.
	t.Setenv(envVarAddr, "http://env-addr:8742")
	setFlag(t, &flagAddr, srv.URL)

	drain := NewDrainCmd()
	var buf bytes.Buffer
	drain.SetOut(&buf)
	require.NoError(t, drain.Execute())
	require.Equal(t, 1, pushCount)
}
