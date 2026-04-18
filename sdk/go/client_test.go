package cq

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

// testClearEnv clears CQ environment variables so tests are isolated from the host.
func testClearEnv(t *testing.T) {
	t.Helper()
	t.Setenv("CQ_ADDR", "")
	t.Setenv("CQ_API_KEY", "")
	t.Setenv("CQ_LOCAL_DB_PATH", "")
}

func newTestClient(t *testing.T) *Client {
	t.Helper()
	testClearEnv(t)
	dbPath := filepath.Join(t.TempDir(), "test.db")
	c, err := NewClient(WithLocalDBPath(dbPath))
	require.NoError(t, err)
	t.Cleanup(func() { _ = c.Close() })
	return c
}

func newTestClientWithRemote(t *testing.T, handler http.Handler) *Client {
	t.Helper()
	testClearEnv(t)
	srv := httptest.NewServer(handler)
	t.Cleanup(srv.Close)
	dbPath := filepath.Join(t.TempDir(), "test.db")
	c, err := NewClient(WithAddr(srv.URL), WithLocalDBPath(dbPath))
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

	c := newTestClient(t)
	require.NotNil(t, c)
}

func TestNewClientWithRemote(t *testing.T) {
	testClearEnv(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()
	dbPath := filepath.Join(t.TempDir(), "test.db")
	c, err := NewClient(WithAddr(srv.URL), WithLocalDBPath(dbPath))
	require.NoError(t, err)
	require.NotNil(t, c)
	_ = c.Close()
}

func TestClientQuery(t *testing.T) {

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

	c := newTestClient(t)
	_, err := c.Confirm(context.Background(), KnowledgeUnit{ID: "ku_00000000000000000000000000ffffff", Tier: Local})
	require.Error(t, err)
}

func TestFlag(t *testing.T) {

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

	c := newTestClient(t)
	_, err := c.Flag(context.Background(), KnowledgeUnit{ID: "ku_00000000000000000000000000ffffff", Tier: Local}, Stale)
	require.Error(t, err)
}

func TestFlagDuplicateRequiresDuplicateOf(t *testing.T) {

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

func TestLifecycle(t *testing.T) {

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
	testClearEnv(t)
	dbPath := filepath.Join(t.TempDir(), "test.db")
	c, err := NewClient(WithAddr("http://127.0.0.1:1"), WithLocalDBPath(dbPath), WithTimeout(1*time.Second))
	require.NoError(t, err)
	t.Cleanup(func() { _ = c.Close() })

	ku, err := c.Propose(context.Background(), ProposeParams{
		Summary: "Fallback", Detail: "D.", Action: "A.", Domains: []string{"api"},
	})

	// Returns FallbackError with transport cause, no RemoteError.
	var fb *FallbackError
	require.ErrorAs(t, err, &fb)
	require.Contains(t, fb.LocalUnit.ID, "ku_")
	require.True(t, errors.Is(fb.Err, errUnreachable))
	var re *RemoteError
	require.False(t, errors.As(fb.Err, &re))

	require.Equal(t, fb.LocalUnit.ID, ku.ID)

	// Stored locally as fallback.
	stats, _ := c.Status(context.Background())
	require.Equal(t, 1, stats.TotalCount)
}

func TestFallbackErrorMessage(t *testing.T) {
	t.Run("with RemoteError cause", func(t *testing.T) {
		fb := &FallbackError{
			LocalUnit: KnowledgeUnit{ID: "ku_01234567890123456789012345678901"},
			Err:       &RemoteError{StatusCode: 401, Detail: "Invalid API key"},
		}
		require.Equal(t,
			"stored locally after remote failure: remote API rejected request (401): Invalid API key",
			fb.Error(),
		)
	})

	t.Run("with sentinel cause", func(t *testing.T) {
		fb := &FallbackError{
			LocalUnit: KnowledgeUnit{ID: "ku_01234567890123456789012345678901"},
			Err:       errUnreachable,
		}
		require.Equal(t,
			"stored locally after remote failure: remote API unreachable",
			fb.Error(),
		)
	})
}

func TestProposeRemoteRejects(t *testing.T) {

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

func TestProposeRemoteAuthRejectFallsBackLocally(t *testing.T) {
	for _, tc := range []struct {
		name   string
		status int
	}{
		{"401 Unauthorized", http.StatusUnauthorized},
		{"403 Forbidden", http.StatusForbidden},
	} {
		t.Run(tc.name, func(t *testing.T) {
			c := newTestClientWithRemote(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(tc.status)
				_, _ = w.Write([]byte(`{"detail":"Invalid API key"}`))
			}))

			ku, err := c.Propose(context.Background(), ProposeParams{
				Summary: "Auth fallback", Detail: "D.", Action: "A.", Domains: []string{"api"},
			})

			// Returns FallbackError carrying the locally-stored unit.
			var fb *FallbackError
			require.ErrorAs(t, err, &fb)
			require.Contains(t, fb.LocalUnit.ID, "ku_")
			require.Equal(t, Local, fb.LocalUnit.Tier)

			// Cause unwraps to RemoteError with the auth status code.
			var re *RemoteError
			require.ErrorAs(t, err, &re)
			require.Equal(t, tc.status, re.StatusCode)

			// Unit returned alongside the error matches the fallback.
			require.Equal(t, fb.LocalUnit.ID, ku.ID)

			// Stored locally.
			stats, _ := c.Status(context.Background())
			require.Equal(t, 1, stats.TotalCount)
		})
	}
}

func TestQueryMergesLocalAndRemote(t *testing.T) {

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
	var fb *FallbackError
	require.ErrorAs(t, err, &fb)

	// Query merges local + remote.
	qr, err := c.Query(ctx, QueryParams{Domains: []string{"api"}})
	require.NoError(t, err)
	require.Len(t, qr.Units, 2)
	require.Equal(t, SourceRemote, qr.Source)
}

func TestQuerySourceLocalWhenNoRemote(t *testing.T) {

	c := newTestClient(t)
	ctx := context.Background()

	_, err := c.Propose(ctx, ProposeParams{
		Summary: "Local only", Detail: "D.", Action: "A.", Domains: []string{"api"},
	})
	require.NoError(t, err)

	qr, err := c.Query(ctx, QueryParams{Domains: []string{"api"}})
	require.NoError(t, err)
	require.Len(t, qr.Units, 1)
	require.Equal(t, SourceLocal, qr.Source)
}

func TestQuerySourceRemoteWhenOnlyRemoteReturnsResults(t *testing.T) {

	c := newTestClientWithRemote(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode([]map[string]any{testRemoteKUJSON("ku_00000000000000000000000000000005")})
	}))

	qr, err := c.Query(context.Background(), QueryParams{Domains: []string{"api"}})
	require.NoError(t, err)
	require.Len(t, qr.Units, 1)
	require.Equal(t, SourceRemote, qr.Source)
}

func TestQuerySourceRemoteWhenRemoteFails(t *testing.T) {

	c := newTestClientWithRemote(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))

	qr, err := c.Query(context.Background(), QueryParams{Domains: []string{"api"}})
	require.NoError(t, err)
	require.Empty(t, qr.Units)
	require.Equal(t, SourceRemote, qr.Source)
}

func TestConfirmLocalUnit(t *testing.T) {

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
	testClearEnv(t)

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
	localOnly, err := NewClient(WithLocalDBPath(dbPath))
	require.NoError(t, err)
	_, err = localOnly.Propose(context.Background(), ProposeParams{
		Summary: "Drain me", Detail: "D.", Action: "A.", Domains: []string{"api"},
	})
	require.NoError(t, err)
	_ = localOnly.Close()

	// Create client with remote and drain.
	c, err := NewClient(WithAddr(srv.URL), WithLocalDBPath(dbPath))
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

	c := newTestClient(t)
	_, err := c.Drain(context.Background())
	require.Error(t, err)
	require.Contains(t, err.Error(), "no remote API configured")
}

func TestDrainableCount(t *testing.T) {

	c := newTestClient(t)
	ctx := context.Background()

	count, err := c.DrainableCount(ctx)
	require.NoError(t, err)
	require.Equal(t, 0, count)

	_, err = c.Propose(ctx, ProposeParams{
		Summary: "Drainable", Detail: "D.", Action: "A.", Domains: []string{"test"},
	})
	require.NoError(t, err)

	_, err = c.Propose(ctx, ProposeParams{
		Summary: "Also drainable", Detail: "D.", Action: "A.", Domains: []string{"test"},
	})
	require.NoError(t, err)

	count, err = c.DrainableCount(ctx)
	require.NoError(t, err)
	require.Equal(t, 2, count)
}

func TestHasRemote(t *testing.T) {

	t.Run("without remote", func(t *testing.T) {

		c := newTestClient(t)
		require.False(t, c.HasRemote())
	})

	t.Run("with remote", func(t *testing.T) {

		c := newTestClientWithRemote(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusOK)
		}))
		require.True(t, c.HasRemote())
	})
}

func TestFlagRemoteUnit(t *testing.T) {

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

func TestStatusLocalOnlyHasTierCounts(t *testing.T) {
	c := newTestClient(t)
	ctx := context.Background()

	_, err := c.Propose(ctx, ProposeParams{
		Summary: "S", Detail: "D.", Action: "A.", Domains: []string{"test"},
	})
	require.NoError(t, err)

	stats, err := c.Status(ctx)
	require.NoError(t, err)
	require.Equal(t, map[Tier]int{Local: 1}, stats.TierCounts)
}

func TestStatusWithRemoteMergesTierCounts(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/stats" && r.Method == "GET" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{
				"total_units": 3,
				"tiers":       map[string]int{"private": 3, "public": 0},
				"domains":     map[string]int{"api": 2},
			})
			return
		}
		// Propose unreachable — forces local fallback.
		w.WriteHeader(http.StatusServiceUnavailable)
	})
	c := newTestClientWithRemote(t, handler)
	ctx := context.Background()

	_, err := c.Propose(ctx, ProposeParams{
		Summary: "Local", Detail: "D.", Action: "A.", Domains: []string{"test"},
	})
	var fb *FallbackError
	require.ErrorAs(t, err, &fb)

	stats, err := c.Status(ctx)
	require.NoError(t, err)
	require.Equal(t, 4, stats.TotalCount)
	require.Equal(t, 1, stats.TierCounts[Local])
	require.Equal(t, 3, stats.TierCounts[Private])
	require.Equal(t, 0, stats.TierCounts[Public])
}

func TestStatusWithRemoteMergesDomainCounts(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/stats" && r.Method == "GET" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{
				"total_units": 5,
				"tiers":       map[string]int{"private": 5, "public": 0},
				"domains":     map[string]int{"api": 3, "db": 2},
			})
			return
		}
		// Propose unreachable — forces local fallback.
		w.WriteHeader(http.StatusServiceUnavailable)
	})
	c := newTestClientWithRemote(t, handler)
	ctx := context.Background()

	// Local unit contributes to the "api" domain so we can verify accumulation.
	_, err := c.Propose(ctx, ProposeParams{
		Summary: "Local", Detail: "D.", Action: "A.", Domains: []string{"api"},
	})
	var fb *FallbackError
	require.ErrorAs(t, err, &fb)

	stats, err := c.Status(ctx)
	require.NoError(t, err)
	// "api" appears locally (1) and remotely (3) — counts must accumulate.
	require.Equal(t, 4, stats.DomainCounts["api"])
	// "db" only appears on the remote.
	require.Equal(t, 2, stats.DomainCounts["db"])
}

func TestStatusRemoteUnreachableStillReturnsLocal(t *testing.T) {
	testClearEnv(t)
	dbPath := filepath.Join(t.TempDir(), "test.db")
	c, err := NewClient(WithAddr("http://127.0.0.1:1"), WithLocalDBPath(dbPath), WithTimeout(1*time.Second))
	require.NoError(t, err)
	t.Cleanup(func() { _ = c.Close() })

	_, err = c.Propose(context.Background(), ProposeParams{
		Summary: "S", Detail: "D.", Action: "A.", Domains: []string{"test"},
	})
	var fb *FallbackError
	require.ErrorAs(t, err, &fb)

	stats, err := c.Status(context.Background())
	require.NoError(t, err)
	require.Equal(t, 1, stats.TotalCount)
	require.Equal(t, map[Tier]int{Local: 1}, stats.TierCounts)
}

func TestStatusIgnoresLocalTierFromRemote(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/stats" && r.Method == "GET" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{
				"total_units": 6,
				"tiers":       map[string]int{"local": 1, "private": 4, "public": 1},
				"domains":     map[string]int{},
			})
			return
		}
		w.WriteHeader(http.StatusServiceUnavailable)
	})
	c := newTestClientWithRemote(t, handler)
	ctx := context.Background()

	_, err := c.Propose(ctx, ProposeParams{
		Summary: "S", Detail: "D.", Action: "A.", Domains: []string{"test"},
	})
	var fb *FallbackError
	require.ErrorAs(t, err, &fb)

	stats, err := c.Status(ctx)
	require.NoError(t, err)
	// Local count comes from the local store (1), not from the remote's "local" tier.
	require.Equal(t, 1, stats.TierCounts[Local])
	require.Equal(t, 4, stats.TierCounts[Private])
	require.Equal(t, 1, stats.TierCounts[Public])
	// Total is local (1) + private (4) + public (1) = 6. The remote's "local: 1" is excluded.
	require.Equal(t, 6, stats.TotalCount)
}

func TestClientQueryPassesPatternToStore(t *testing.T) {
	c := newTestClient(t)

	_, err := c.Propose(context.Background(), ProposeParams{
		Summary: "s", Detail: "d", Action: "a",
		Domains: []string{"api"},
		Pattern: "api-client",
	})
	require.NoError(t, err)

	_, err = c.Propose(context.Background(), ProposeParams{
		Summary: "s2", Detail: "d2", Action: "a2",
		Domains: []string{"api"},
	})
	require.NoError(t, err)

	withPattern, err := c.Query(context.Background(), QueryParams{
		Domains: []string{"api"},
		Pattern: "api-client",
	})
	require.NoError(t, err)
	require.NotEmpty(t, withPattern.Units)
	require.Equal(t, "s", withPattern.Units[0].Insight.Summary, "the unit with matching pattern should rank first")
}
