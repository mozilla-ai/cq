package cmd

import (
	"bytes"
	"net/http"
	"strings"
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

func TestStatusTextShowsTierBreakdown(t *testing.T) {
	testSetup(t)
	withFakeRemote(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"total_count":7,"tier_counts":{"private":4,"public":3},"domain_counts":{}}`))
	}))

	status := NewStatusCmd()
	var out bytes.Buffer
	status.SetOut(&out)
	status.SetArgs([]string{})
	require.NoError(t, status.Execute())

	got := out.String()
	require.Contains(t, got, "By tier:")
	require.Contains(t, got, "private")
	require.Contains(t, got, "public")
	require.Contains(t, got, "Knowledge units: 7")
}

func TestStatusTextOmitsTierBreakdownWhenEmpty(t *testing.T) {
	testSetup(t)

	status := NewStatusCmd()
	var out bytes.Buffer
	status.SetOut(&out)
	status.SetArgs([]string{})
	require.NoError(t, status.Execute())
	require.NotContains(t, out.String(), "By tier:")
}

func TestStatusTextShowsCompactDomainsAfterConfidence(t *testing.T) {
	testSetup(t)
	withFakeRemote(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"total_count":23,"tier_counts":{"private":23},` +
			`"domain_counts":{"a":5,"b":4,"c":3,"d":3,"e":2,"f":2,"g":1,"h":1,"i":1,"j":1}}`))
	}))

	status := NewStatusCmd()
	var out bytes.Buffer
	status.SetOut(&out)
	status.SetArgs([]string{})
	require.NoError(t, status.Execute())

	got := out.String()
	require.Contains(t, got, "Domains: 10 total")
	require.Contains(t, got, "a (5)")       // most-tagged shown first
	require.Contains(t, got, "... +2 more") // 10 distinct, 8 shown, 2 truncated
	require.NotContains(t, got, ", ... +")  // no trailing comma before the ellipsis
	// Domains are the least important section, so they sit last.
	require.Less(t, strings.Index(got, "Confidence distribution"), strings.Index(got, "Domains:"))
}

func TestStatusWarnsOnRemoteFailure(t *testing.T) {
	testSetup(t)
	withFakeRemote(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))

	status := NewStatusCmd()
	var out, errBuf bytes.Buffer
	status.SetOut(&out)
	status.SetErr(&errBuf)
	status.SetArgs([]string{})
	require.NoError(t, status.Execute())
	require.Contains(t, errBuf.String(), "warning:")
	require.Contains(t, errBuf.String(), "remote stats unavailable")
}
