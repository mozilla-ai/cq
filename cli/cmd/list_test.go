package cmd

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"testing"

	"github.com/stretchr/testify/require"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

const (
	// listBodyEmpty is a member listing that carries no units.
	listBodyEmpty = `{"data":[],"facets":{"domains":{},"languages":{},"frameworks":{}},"next_cursor":""}`

	// listPath is the member listing path the SDK requests.
	listPath = "/api/v1/knowledge/me"
)

func TestListJSONFormat(t *testing.T) {
	testSetup(t)

	body := fmt.Sprintf(
		`{"data":[%s],"facets":{"domains":{"api":2},"languages":{},"frameworks":{}},"next_cursor":"cursor_next"}`,
		testOwnUnitJSON("ku_00000000000000000000000000000001", cq.Approved, 0.85, "json summary"),
	)
	testListRemote(t, body)

	list := NewListCmd()
	var buf bytes.Buffer
	list.SetOut(&buf)
	list.SetArgs([]string{"--format", "json"})
	require.NoError(t, list.Execute())

	var result cq.ListResult
	require.NoError(t, json.Unmarshal(buf.Bytes(), &result))
	require.Len(t, result.Units, 1)
	require.Equal(t, cq.Approved, result.Units[0].Status)

	// Facets and the cursor must survive into JSON, otherwise an agent cannot
	// page through the listing or see the tag counts.
	require.Equal(t, 2, result.Facets.Domains["api"])
	require.Equal(t, "cursor_next", result.NextCursor)
}

func TestListLastPageOmitsNextPageHint(t *testing.T) {
	testSetup(t)

	body := fmt.Sprintf(
		`{"data":[%s],"facets":{"domains":{},"languages":{},"frameworks":{}},"next_cursor":""}`,
		testOwnUnitJSON("ku_00000000000000000000000000000001", cq.Approved, 0.85, "only summary"),
	)
	testListRemote(t, body)

	list := NewListCmd()
	var buf bytes.Buffer
	list.SetOut(&buf)
	list.SetArgs([]string{})
	require.NoError(t, list.Execute())
	require.NotContains(t, buf.String(), "--cursor")
}

func TestListNoUnits(t *testing.T) {
	testSetup(t)

	testListRemote(t, listBodyEmpty)

	list := NewListCmd()
	var buf bytes.Buffer
	list.SetOut(&buf)
	list.SetArgs([]string{})
	require.NoError(t, list.Execute())
	require.Contains(t, buf.String(), "No knowledge units found.")
}

func TestListPrintsNextPageHint(t *testing.T) {
	testSetup(t)

	body := fmt.Sprintf(
		`{"data":[%s],"facets":{"domains":{},"languages":{},"frameworks":{}},"next_cursor":"cursor_next"}`,
		testOwnUnitJSON("ku_00000000000000000000000000000001", cq.Approved, 0.85, "paged summary"),
	)
	testListRemote(t, body)

	list := NewListCmd()
	var buf bytes.Buffer
	list.SetOut(&buf)
	list.SetArgs([]string{})
	require.NoError(t, list.Execute())
	require.Contains(t, buf.String(), "--cursor cursor_next")
}

func TestListRejectsUnknownStatus(t *testing.T) {
	testSetup(t)

	list := NewListCmd()
	list.SetArgs([]string{"--status", "approvd"})
	err := list.Execute()
	require.ErrorContains(t, err, "approvd")
	require.ErrorContains(t, err, "pending")
}

func TestListRequiresRemote(t *testing.T) {
	testSetup(t)

	list := NewListCmd()
	list.SetOut(io.Discard)
	list.SetArgs([]string{})
	require.ErrorContains(t, list.Execute(), "no remote API configured")
}

func TestListSendsEveryFilter(t *testing.T) {
	testSetup(t)

	query := testListRemote(t, listBodyEmpty)

	list := NewListCmd()
	list.SetOut(io.Discard)
	list.SetArgs([]string{
		"--domain", "api",
		"--domain", "payments",
		"--language", "go",
		"--framework", "fastapi",
		"--pattern", "shell-quoting",
		"--search", "nektos/act",
		"--status", "pending",
		"--limit", "7",
		"--cursor", "cursor_abc",
	})
	require.NoError(t, list.Execute())

	qv := query()
	require.Equal(t, []string{"api", "payments"}, qv["domain"])
	require.Equal(t, []string{"go"}, qv["language"])
	require.Equal(t, []string{"fastapi"}, qv["framework"])
	require.Equal(t, "shell-quoting", qv.Get("pattern"))
	require.Equal(t, "nektos/act", qv.Get("q"))
	require.Equal(t, "pending", qv.Get("status"))
	require.Equal(t, "7", qv.Get("limit"))
	require.Equal(t, "cursor_abc", qv.Get("cursor"))
}

func TestListTextAlignsColumnsAcrossRows(t *testing.T) {
	testSetup(t)

	// 'approved' is one character longer than 'pending', so unpadded output
	// starts the two summaries at different offsets.
	body := fmt.Sprintf(
		`{"data":[%s,%s],"facets":{"domains":{},"languages":{},"frameworks":{}},"next_cursor":""}`,
		testOwnUnitJSON("ku_00000000000000000000000000000001", cq.Approved, 0.85, "first summary"),
		testOwnUnitJSON("ku_00000000000000000000000000000002", cq.Pending, 0.5, "second summary"),
	)
	testListRemote(t, body)

	list := NewListCmd()
	var buf bytes.Buffer
	list.SetOut(&buf)
	list.SetArgs([]string{})
	require.NoError(t, list.Execute())

	header := testLineContaining(t, buf.String(), "SUMMARY")
	first := testLineContaining(t, buf.String(), "first summary")
	second := testLineContaining(t, buf.String(), "second summary")

	require.Equal(t,
		strings.Index(first, "first summary"),
		strings.Index(second, "second summary"),
		"the summary column must start at the same offset on every row")
	require.Equal(t,
		strings.Index(header, "SUMMARY"),
		strings.Index(first, "first summary"),
		"the summary column must start under its own heading")
}

func TestListTextShowsReviewStatus(t *testing.T) {
	testSetup(t)

	// The summary must not contain the status word, or the line would carry
	// 'rejected' even with the status column dropped.
	body := fmt.Sprintf(
		`{"data":[%s],"facets":{"domains":{},"languages":{},"frameworks":{}},"next_cursor":""}`,
		testOwnUnitJSON("ku_00000000000000000000000000000001", cq.Rejected, 0.35, "a wrong insight"),
	)
	testListRemote(t, body)

	list := NewListCmd()
	var buf bytes.Buffer
	list.SetOut(&buf)
	list.SetArgs([]string{})
	require.NoError(t, list.Execute())

	line := testLineContaining(t, buf.String(), "a wrong insight")
	require.Contains(t, line, "ku_00000000000000000000000000000001")
	require.Contains(t, line, "rejected")
	require.Contains(t, line, "35%")
}

func TestListUnsupportedFormat(t *testing.T) {
	testSetup(t)

	list := NewListCmd()
	list.SetArgs([]string{"--format", "xml"})
	require.Error(t, list.Execute())
}

// testLineContaining returns the first output line holding substr.
func testLineContaining(t *testing.T, out string, substr string) string {
	t.Helper()

	for _, line := range strings.Split(out, "\n") {
		if strings.Contains(line, substr) {
			return line
		}
	}

	t.Fatalf("no output line contains '%s'", substr)

	return ""
}

// testListRemote serves body at the member listing path and returns an
// accessor for the query parameters the SDK sent.
func testListRemote(t *testing.T, body string) func() url.Values {
	t.Helper()

	var (
		mu sync.Mutex
		qv url.Values
	)

	withFakeRemote(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != listPath {
			http.NotFound(w, r)

			return
		}

		mu.Lock()
		qv = r.URL.Query()
		mu.Unlock()

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(body))
	}))

	return func() url.Values {
		mu.Lock()
		defer mu.Unlock()

		return qv
	}
}

// testOwnUnitJSON builds the member shape, where a unit's review state sits
// beside the unit's own fields rather than in a nested object.
func testOwnUnitJSON(id string, status cq.ReviewStatus, confidence float64, summary string) string {
	return fmt.Sprintf(
		`{"id":%q,"version":1,"domains":["api"],`+
			`"insight":{"summary":%q,"detail":"d","action":"a"},`+
			`"context":{"languages":[],"frameworks":[],"pattern":""},`+
			`"evidence":{"confidence":%v,"confirmations":1},`+
			`"tier":"private","flags":[],"status":%q}`,
		id, summary, confidence, status,
	)
}
