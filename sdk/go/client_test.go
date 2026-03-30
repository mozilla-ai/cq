package cq

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

// testNoRemote overrides any CQ_TEAM_ADDR or CQ_ADDR env var to ensure local-only operation.
func testNoRemote() ClientOption {
	return WithAddr("")
}

func newTestClient(t *testing.T) *Client {
	t.Helper()
	dbPath := filepath.Join(t.TempDir(), "test.db")
	c, err := NewClient(testNoRemote(), WithAPIKey(""), WithLocalDBPath(dbPath))
	require.NoError(t, err)
	t.Cleanup(func() { _ = c.Close() })
	return c
}

func newTestClientWithRemote(t *testing.T, handler http.Handler) *Client {
	t.Helper()
	srv := httptest.NewServer(handler)
	t.Cleanup(srv.Close)
	dbPath := filepath.Join(t.TempDir(), "test.db")
	c, err := NewClient(WithAddr(srv.URL), WithAPIKey(""), WithLocalDBPath(dbPath))
	require.NoError(t, err)
	t.Cleanup(func() { _ = c.Close() })
	return c
}

func testRemoteKUJSON(id string) map[string]any {
	return map[string]any{
		"id":      id,
		"version": 1,
		"domains": []string{"api"},
		"insight": map[string]string{"summary": "S", "detail": "D", "action": "A"},
		"context": map[string]any{"languages": []string{"go"}, "frameworks": []any{}, "pattern": ""},
		"evidence": map[string]any{
			"confidence":     0.5,
			"confirmations":  1,
			"first_observed": "2026-03-28T12:00:00Z",
			"last_confirmed": "2026-03-28T12:00:00Z",
		},
		"tier":  "local",
		"flags": []any{},
	}
}

// -- Local-only tests --

func TestNewClientLocalOnly(t *testing.T) {
	t.Parallel()
	c := newTestClient(t)
	require.NotNil(t, c)
}

func TestNewClientWithRemote(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()
	dbPath := filepath.Join(t.TempDir(), "test.db")
	c, err := NewClient(WithAddr(srv.URL), WithAPIKey(""), WithLocalDBPath(dbPath))
	require.NoError(t, err)
	require.NotNil(t, c)
	_ = c.Close()
}

func TestClientQuery(t *testing.T) {
	t.Parallel()
	c := newTestClient(t)
	ctx := context.Background()

	_, err := c.Propose(ctx, ProposeParams{
		Summary: "Test insight", Detail: "Detail.", Action: "Action.",
		Domains: []string{"api", "testing"},
	})
	require.NoError(t, err)

	qr, err := c.Query(ctx, QueryParams{Domains: []string{"api"}})
	require.NoError(t, err)
	require.Len(t, qr.Units, 1)
	require.Equal(t, "Test insight", qr.Units[0].Insight.Summary)
	require.Equal(t, Local, qr.Units[0].Tier)
}

func TestPropose(t *testing.T) {
	t.Parallel()
	c := newTestClient(t)
	ctx := context.Background()

	ku, err := c.Propose(ctx, ProposeParams{
		Summary: "Stripe 402", Detail: "Check error.code.", Action: "Handle card_declined.",
		Domains: []string{"api", "stripe"}, Languages: []string{"go"}, Frameworks: []string{"net/http"},
		Pattern: "api-client", CreatedBy: "test-agent",
	})
	require.NoError(t, err)
	require.Contains(t, ku.ID, "ku_")
	require.Equal(t, "Stripe 402", ku.Insight.Summary)
	require.Equal(t, []string{"go"}, ku.Context.Languages)
	require.Equal(t, Local, ku.Tier)
	require.InDelta(t, 0.5, ku.Evidence.Confidence, 0.001)
}

func TestConfirm(t *testing.T) {
	t.Parallel()
	c := newTestClient(t)
	ctx := context.Background()

	ku, err := c.Propose(ctx, ProposeParams{
		Summary: "Confirmable", Detail: "D.", Action: "A.", Domains: []string{"test"},
	})
	require.NoError(t, err)

	confirmed, err := c.Confirm(ctx, ku)
	require.NoError(t, err)
	require.Greater(t, confirmed.Evidence.Confidence, ku.Evidence.Confidence)
	require.Equal(t, ku.Evidence.Confirmations+1, confirmed.Evidence.Confirmations)
}

func TestConfirmNotFound(t *testing.T) {
	t.Parallel()
	c := newTestClient(t)
	_, err := c.Confirm(context.Background(), KnowledgeUnit{ID: "ku_00000000000000000000000000ffffff", Tier: Local})
	require.Error(t, err)
}

func TestFlag(t *testing.T) {
	t.Parallel()
	c := newTestClient(t)
	ctx := context.Background()

	ku, err := c.Propose(ctx, ProposeParams{
		Summary: "Flaggable", Detail: "D.", Action: "A.", Domains: []string{"test"},
	})
	require.NoError(t, err)

	flagged, err := c.Flag(ctx, ku, Stale)
	require.NoError(t, err)
	require.Less(t, flagged.Evidence.Confidence, ku.Evidence.Confidence)
	require.Len(t, flagged.Flags, 1)
	require.Equal(t, Stale, flagged.Flags[0].Reason)
}

func TestFlagNotFound(t *testing.T) {
	t.Parallel()
	c := newTestClient(t)
	_, err := c.Flag(context.Background(), KnowledgeUnit{ID: "ku_00000000000000000000000000ffffff", Tier: Local}, Stale)
	require.Error(t, err)
}

func TestFlagDuplicateRequiresDuplicateOf(t *testing.T) {
	t.Parallel()
	c := newTestClient(t)
	ctx := context.Background()

	ku, err := c.Propose(ctx, ProposeParams{
		Summary: "Flaggable", Detail: "D.", Action: "A.", Domains: []string{"test"},
	})
	require.NoError(t, err)

	_, err = c.Flag(ctx, ku, Duplicate)
	require.Error(t, err)
	require.Contains(t, err.Error(), "WithDuplicateOf")
}

func TestFlagDuplicateWithValidDuplicateOf(t *testing.T) {
	t.Parallel()
	c := newTestClient(t)
	ctx := context.Background()

	original, err := c.Propose(ctx, ProposeParams{
		Summary: "Original", Detail: "D.", Action: "A.", Domains: []string{"test"},
	})
	require.NoError(t, err)

	duplicate, err := c.Propose(ctx, ProposeParams{
		Summary: "Duplicate", Detail: "D.", Action: "A.", Domains: []string{"test"},
	})
	require.NoError(t, err)

	flagged, err := c.Flag(ctx, duplicate, Duplicate, WithDuplicateOf(original.ID))
	require.NoError(t, err)
	require.Len(t, flagged.Flags, 1)
	require.Equal(t, Duplicate, flagged.Flags[0].Reason)
	require.Equal(t, original.ID, flagged.Flags[0].DuplicateOf)
}

func TestFlagDuplicateRejectsInvalidID(t *testing.T) {
	t.Parallel()
	c := newTestClient(t)
	ctx := context.Background()

	ku, err := c.Propose(ctx, ProposeParams{
		Summary: "Flaggable", Detail: "D.", Action: "A.", Domains: []string{"test"},
	})
	require.NoError(t, err)

	_, err = c.Flag(ctx, ku, Duplicate, WithDuplicateOf("bad-id"))
	require.Error(t, err)
	require.Contains(t, err.Error(), "invalid")
}

func TestStatus(t *testing.T) {
	t.Parallel()
	c := newTestClient(t)
	ctx := context.Background()

	stats, err := c.Status(ctx)
	require.NoError(t, err)
	require.Equal(t, 0, stats.TotalCount)

	_, err = c.Propose(ctx, ProposeParams{
		Summary: "S.", Detail: "D.", Action: "A.", Domains: []string{"test"},
	})
	require.NoError(t, err)

	stats, err = c.Status(ctx)
	require.NoError(t, err)
	require.Equal(t, 1, stats.TotalCount)
}

func TestPromptMethod(t *testing.T) {
	t.Parallel()
	c := newTestClient(t)
	require.NotEmpty(t, c.Prompt())
}

func TestLifecycle(t *testing.T) {
	t.Parallel()
	c := newTestClient(t)
	ctx := context.Background()

	ku, err := c.Propose(ctx, ProposeParams{
		Summary: "Lifecycle test", Detail: "Full round-trip.", Action: "Verify lifecycle.",
		Domains: []string{"testing", "e2e"},
	})
	require.NoError(t, err)

	qr, err := c.Query(ctx, QueryParams{Domains: []string{"testing"}})
	require.NoError(t, err)
	require.Len(t, qr.Units, 1)
	require.Equal(t, ku.ID, qr.Units[0].ID)

	confirmed, err := c.Confirm(ctx, ku)
	require.NoError(t, err)
	require.Greater(t, confirmed.Evidence.Confidence, ku.Evidence.Confidence)

	flagged, err := c.Flag(ctx, ku, Incorrect)
	require.NoError(t, err)
	require.Less(t, flagged.Evidence.Confidence, confirmed.Evidence.Confidence)

	stats, err := c.Status(ctx)
	require.NoError(t, err)
	require.Equal(t, 1, stats.TotalCount)
}

// -- Remote integration tests --

func TestProposeRemoteReachable(t *testing.T) {
	t.Parallel()
	c := newTestClientWithRemote(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusCreated)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(testRemoteKUJSON("ku_00000000000000000000000000000001"))
	}))
	ctx := context.Background()

	ku, err := c.Propose(ctx, ProposeParams{
		Summary: "Test", Detail: "D.", Action: "A.", Domains: []string{"api"},
	})
	require.NoError(t, err)
	require.Equal(t, "ku_00000000000000000000000000000001", ku.ID)

	// Not stored locally; remote accepted it.
	stats, _ := c.Status(ctx)
	require.Equal(t, 0, stats.TotalCount)
}

func TestProposeRemoteUnreachable(t *testing.T) {
	t.Parallel()
	dbPath := filepath.Join(t.TempDir(), "test.db")
	c, err := NewClient(WithAddr("http://127.0.0.1:1"), WithAPIKey(""), WithLocalDBPath(dbPath), WithTimeout(1*time.Second))
	require.NoError(t, err)
	t.Cleanup(func() { _ = c.Close() })

	ku, err := c.Propose(context.Background(), ProposeParams{
		Summary: "Fallback", Detail: "D.", Action: "A.", Domains: []string{"api"},
	})
	require.NoError(t, err)
	require.Contains(t, ku.ID, "ku_")

	// Stored locally as fallback.
	stats, _ := c.Status(context.Background())
	require.Equal(t, 1, stats.TotalCount)
}

func TestProposeRemoteRejects(t *testing.T) {
	t.Parallel()
	c := newTestClientWithRemote(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusUnprocessableEntity)
		_, _ = w.Write([]byte("bad request"))
	}))

	_, err := c.Propose(context.Background(), ProposeParams{
		Summary: "Rejected", Detail: "D.", Action: "A.", Domains: []string{"api"},
	})
	require.Error(t, err)
	var remoteErr *RemoteError
	require.ErrorAs(t, err, &remoteErr)
	require.Equal(t, 422, remoteErr.StatusCode)
}

func TestQueryMergesLocalAndRemote(t *testing.T) {
	t.Parallel()
	c := newTestClientWithRemote(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/propose" {
			// Unreachable for propose; forces local storage.
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode([]map[string]any{testRemoteKUJSON("ku_00000000000000000000000000000003")})
	}))
	ctx := context.Background()

	// Propose falls back to local (remote unreachable for propose).
	_, err := c.Propose(ctx, ProposeParams{
		Summary: "Local insight", Detail: "D.", Action: "A.", Domains: []string{"api"},
	})
	require.NoError(t, err)

	// Query merges local + remote.
	qr, err := c.Query(ctx, QueryParams{Domains: []string{"api"}})
	require.NoError(t, err)
	require.Len(t, qr.Units, 2)
}

func TestConfirmLocalUnit(t *testing.T) {
	t.Parallel()
	var confirmedRemotely bool
	c := newTestClientWithRemote(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/propose" {
			// Unreachable; forces local fallback.
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}

		if r.Method == "POST" && len(r.URL.Path) > 9 && r.URL.Path[:9] == "/confirm/" {
			confirmedRemotely = true
		}

		w.WriteHeader(http.StatusNotFound)
	}))
	ctx := context.Background()

	ku, _ := c.Propose(ctx, ProposeParams{
		Summary: "S", Detail: "D.", Action: "A.", Domains: []string{"api"},
	})
	require.Equal(t, Local, ku.Tier)

	confirmed, err := c.Confirm(ctx, ku)
	require.NoError(t, err)
	require.Greater(t, confirmed.Evidence.Confidence, ku.Evidence.Confidence)
	// Local unit confirmed locally; should NOT hit remote.
	require.False(t, confirmedRemotely)
}

func TestConfirmRemoteUnit(t *testing.T) {
	t.Parallel()
	var confirmedRemotely bool
	c := newTestClientWithRemote(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "POST" && len(r.URL.Path) > 9 && r.URL.Path[:9] == "/confirm/" {
			confirmedRemotely = true
			w.Header().Set("Content-Type", "application/json")
			resp := testRemoteKUJSON(r.URL.Path[9:])
			resp["evidence"].(map[string]any)["confidence"] = 0.8
			_ = json.NewEncoder(w).Encode(resp)

			return
		}

		w.WriteHeader(http.StatusNotFound)
	}))

	// Simulate a unit that came from a remote query (not in local store).
	remoteUnit := KnowledgeUnit{ID: "ku_00000000000000000000000000000002", Tier: Private}
	confirmed, err := c.Confirm(context.Background(), remoteUnit)
	require.NoError(t, err)
	require.True(t, confirmedRemotely)
	require.Equal(t, "ku_00000000000000000000000000000002", confirmed.ID)
}

func TestDrain(t *testing.T) {
	t.Parallel()
	var pushCount int
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/propose" && r.Method == "POST" {
			pushCount++
			w.WriteHeader(http.StatusCreated)
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(testRemoteKUJSON("ku_00000000000000000000000000000004"))
			return
		}
		w.WriteHeader(http.StatusServiceUnavailable)
	})
	srv := httptest.NewServer(handler)
	defer srv.Close()

	dbPath := filepath.Join(t.TempDir(), "test.db")

	// Seed local data with a local-only client.
	localOnly, err := NewClient(testNoRemote(), WithAPIKey(""), WithLocalDBPath(dbPath))
	require.NoError(t, err)
	_, err = localOnly.Propose(context.Background(), ProposeParams{
		Summary: "Drain me", Detail: "D.", Action: "A.", Domains: []string{"api"},
	})
	require.NoError(t, err)
	_ = localOnly.Close()

	// Create client with remote and drain.
	c, err := NewClient(WithAddr(srv.URL), WithAPIKey(""), WithLocalDBPath(dbPath))
	require.NoError(t, err)
	defer func() { _ = c.Close() }()

	dr, err := c.Drain(context.Background())
	require.NoError(t, err)
	require.Equal(t, 1, dr.Pushed)
	require.Empty(t, dr.Warnings)
	require.Equal(t, 1, pushCount)

	// Local store should be empty after drain.
	stats, _ := c.Status(context.Background())
	require.Equal(t, 0, stats.TotalCount)
}

func TestDrainNoRemote(t *testing.T) {
	t.Parallel()
	c := newTestClient(t)
	_, err := c.Drain(context.Background())
	require.Error(t, err)
	require.Contains(t, err.Error(), "no remote API configured")
}

func TestFlagRemoteUnit(t *testing.T) {
	t.Parallel()
	var received map[string]any
	c := newTestClientWithRemote(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "POST" && len(r.URL.Path) > 6 && r.URL.Path[:6] == "/flag/" {
			_ = json.NewDecoder(r.Body).Decode(&received)
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(testRemoteKUJSON(r.URL.Path[6:]))

			return
		}

		w.WriteHeader(http.StatusNotFound)
	}))

	remoteUnit := KnowledgeUnit{ID: "ku_00000000000000000000000000000002", Tier: Private}
	flagged, err := c.Flag(context.Background(), remoteUnit, Stale, WithDetail("outdated info"))
	require.NoError(t, err)
	require.Equal(t, "ku_00000000000000000000000000000002", flagged.ID)
	require.Equal(t, "stale", received["reason"])
	require.Equal(t, "outdated info", received["detail"])
}

func TestQueryLimitCappedAt50(t *testing.T) {
	t.Parallel()
	c := newTestClient(t)
	ctx := context.Background()

	_, err := c.Propose(ctx, ProposeParams{
		Summary: "S", Detail: "D.", Action: "A.", Domains: []string{"test"},
	})
	require.NoError(t, err)

	qr, err := c.Query(ctx, QueryParams{Domains: []string{"test"}, Limit: 200})
	require.NoError(t, err)
	// Should not error; limit is silently capped.
	require.LessOrEqual(t, len(qr.Units), 50)
}
