package cq

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/mozilla-ai/cq/sdk/go/discovery"
)

// staticResolver is a test double for apiResolver that returns a fixed
// NodeInfo without touching the disk or network.
// An empty apiBaseURL produces the same default behavior the real
// resolver applies for a node without a discovery document.
type staticResolver struct {
	apiBaseURL string
}

func (s staticResolver) Resolve(_ context.Context, addr string) (discovery.NodeInfo, error) {
	base := s.apiBaseURL
	if base == "" {
		base = addr + discovery.DefaultAPIPath
	}
	return discovery.NodeInfo{APIBaseURL: base, APIVersion: discovery.DefaultAPIVersion}, nil
}

func TestRemoteQuery(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/api/v1/knowledge", r.URL.Path)
		require.Equal(t, "GET", r.Method)
		require.Equal(t, []string{"api", "testing"}, r.URL.Query()["domains"])

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"data": []map[string]any{testRemoteKUJSON("ku_00000000000000000000000000000002")},
		})
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	units, err := rc.query(context.Background(), QueryParams{Domains: []string{"api", "testing"}})
	require.NoError(t, err)
	require.Len(t, units, 1)
	require.Equal(t, "ku_00000000000000000000000000000002", units[0].ID)
	require.Equal(t, "S", units[0].Insight.Summary)
}

func TestRemoteQueryWithAuth(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "Bearer test-token", r.Header.Get("Authorization"))
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "test-token", 5*time.Second, staticResolver{})
	units, err := rc.query(context.Background(), QueryParams{Domains: []string{"api"}})
	require.NoError(t, err)
	require.Empty(t, units)
}

func TestRemoteQueryServerError(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	units, err := rc.query(context.Background(), QueryParams{Domains: []string{"api"}})
	require.Nil(t, units)
	require.ErrorIs(t, err, errUnreachable)
}

func TestRemoteQueryRejectsBareArrayResponse(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode([]map[string]any{testRemoteKUJSON("ku_00000000000000000000000000000002")})
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	units, err := rc.query(context.Background(), QueryParams{Domains: []string{"api"}})
	require.Nil(t, units)
	require.Error(t, err)
	require.Contains(t, err.Error(), "decoding")
}

func TestRemoteQueryRejectsMissingDataKey(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"results": []}`))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	units, err := rc.query(context.Background(), QueryParams{Domains: []string{"api"}})
	require.Nil(t, units)
	require.Error(t, err)
	require.Contains(t, err.Error(), "data")
}

func TestRemoteQueryRejectsNullDataField(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"data": null}`))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	units, err := rc.query(context.Background(), QueryParams{Domains: []string{"api"}})
	require.Nil(t, units)
	require.Error(t, err)
	require.Contains(t, err.Error(), "data")
}

func TestRemoteQueryRejectsMalformedBody(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte("not json"))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	units, err := rc.query(context.Background(), QueryParams{Domains: []string{"api"}})
	require.Nil(t, units)
	require.Error(t, err)
}

func TestRemoteQueryTransportError(t *testing.T) {
	t.Parallel()
	rc := newRemoteClient("http://127.0.0.1:1", "", 1*time.Second, staticResolver{})
	units, err := rc.query(context.Background(), QueryParams{Domains: []string{"api"}})
	require.Nil(t, units)
	require.ErrorIs(t, err, errUnreachable)
}

func TestRemotePropose(t *testing.T) {
	t.Parallel()
	var received map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/api/v1/knowledge", r.URL.Path)
		require.Equal(t, "POST", r.Method)
		_ = json.NewDecoder(r.Body).Decode(&received)

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(w).Encode(testRemoteKUJSON("ku_00000000000000000000000000000005"))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	ku := KnowledgeUnit{
		Domains: []string{"api"},
		Insight: Insight{Summary: "S", Detail: "D", Action: "A"},
	}
	result, err := rc.propose(context.Background(), ku)
	require.NoError(t, err)
	require.Equal(t, "ku_00000000000000000000000000000005", result.ID)
	require.Equal(t, []any{"api"}, received["domains"])
}

func TestRemoteProposeRejected(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusUnprocessableEntity)
		_, _ = w.Write([]byte("validation failed"))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	ku := KnowledgeUnit{Domains: []string{"api"}, Insight: Insight{Summary: "S", Detail: "D", Action: "A"}}
	_, err := rc.propose(context.Background(), ku)
	require.Error(t, err)

	var remoteErr *RemoteError
	require.ErrorAs(t, err, &remoteErr)
	require.Equal(t, 422, remoteErr.StatusCode)
}

func TestRemoteClientResolvesAPIBaseURLViaDiscovery(t *testing.T) {
	t.Parallel()
	var capturedPath string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == discovery.WellKnownPath {
			http.NotFound(w, r)
			return
		}
		capturedPath = r.URL.Path
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"data": []}`))
	}))
	defer srv.Close()

	resolver, err := discovery.New(discovery.WithCacheDir(t.TempDir()))
	require.NoError(t, err)
	rc := newRemoteClient(srv.URL, "", 5*time.Second, resolver)
	_, _ = rc.query(context.Background(), QueryParams{Domains: []string{"api"}})

	require.Equal(t, "/api/v1/knowledge", capturedPath)
}

func TestRemoteConfirm(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/api/v1/knowledge/ku_00000000000000000000000000000005/confirmations", r.URL.Path)
		require.Equal(t, "POST", r.Method)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(testRemoteKUJSON("ku_00000000000000000000000000000005"))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	ku, err := rc.confirm(context.Background(), "ku_00000000000000000000000000000005")
	require.NoError(t, err)
	require.Equal(t, "ku_00000000000000000000000000000005", ku.ID)
}

func TestRemoteFlag(t *testing.T) {
	t.Parallel()
	var received map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/api/v1/knowledge/ku_00000000000000000000000000000005/flags", r.URL.Path)
		_ = json.NewDecoder(r.Body).Decode(&received)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(testRemoteKUJSON("ku_00000000000000000000000000000005"))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	ku, err := rc.flag(context.Background(), "ku_00000000000000000000000000000005", Stale, flagConfig{})
	require.NoError(t, err)
	require.NotNil(t, ku)
	require.Equal(t, "stale", received["reason"])
}

func TestRemoteFlagWithDetailAndDuplicate(t *testing.T) {
	t.Parallel()
	var received map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewDecoder(r.Body).Decode(&received)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(testRemoteKUJSON("ku_00000000000000000000000000000005"))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	cfg := flagConfig{detail: "it is old", duplicateOf: "ku_00000000000000000000000000000002"}
	_, err := rc.flag(context.Background(), "ku_00000000000000000000000000000005", Duplicate, cfg)
	require.NoError(t, err)
	require.Equal(t, "duplicate", received["reason"])
	require.Equal(t, "it is old", received["detail"])
	require.Equal(t, "ku_00000000000000000000000000000002", received["duplicate_of"])
}

func TestRemoteFlagOmitsEmptyFields(t *testing.T) {
	t.Parallel()
	var received map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewDecoder(r.Body).Decode(&received)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(testRemoteKUJSON("ku_00000000000000000000000000000005"))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	_, err := rc.flag(context.Background(), "ku_00000000000000000000000000000005", Stale, flagConfig{})
	require.NoError(t, err)
	_, hasDetail := received["detail"]
	_, hasDup := received["duplicate_of"]
	require.False(t, hasDetail, "empty detail should not be sent")
	require.False(t, hasDup, "empty duplicate_of should not be sent")
}

func TestRemoteQuerySendsPluralParamNames(t *testing.T) {
	t.Parallel()

	t.Run("single values", func(t *testing.T) {
		t.Parallel()
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			require.NotEmpty(t, r.URL.Query()["domains"], "should send 'domains' not 'domain'")
			require.Empty(t, r.URL.Query()["domain"], "should not send singular 'domain'")

			require.Equal(t, []string{"go"}, r.URL.Query()["languages"])
			require.Equal(t, []string{"grpc"}, r.URL.Query()["frameworks"])

			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
		}))
		defer srv.Close()

		rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
		_, _ = rc.query(context.Background(), QueryParams{
			Domains:    []string{"api"},
			Languages:  []string{"go"},
			Frameworks: []string{"grpc"},
		})
	})

	t.Run("multiple values", func(t *testing.T) {
		t.Parallel()
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			require.Equal(t, []string{"api", "testing"}, r.URL.Query()["domains"])
			require.Equal(t, []string{"python", "go"}, r.URL.Query()["languages"])
			require.Equal(t, []string{"grpc", "http"}, r.URL.Query()["frameworks"])

			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{"data": []map[string]any{}})
		}))
		defer srv.Close()

		rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
		_, _ = rc.query(context.Background(), QueryParams{
			Domains:    []string{"api", "testing"},
			Languages:  []string{"python", "go"},
			Frameworks: []string{"grpc", "http"},
		})
	})
}

func TestRemoteStats(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/api/v1/knowledge/stats", r.URL.Path)
		require.Equal(t, "GET", r.Method)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"total_count":   5,
			"tier_counts":   map[string]int{"private": 4, "public": 1},
			"domain_counts": map[string]int{"api": 3, "db": 2},
		})
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	rs, err := rc.stats(context.Background())
	require.NoError(t, err)
	require.Equal(t, 5, rs.TotalCount)
	require.Equal(t, map[Tier]int{Private: 4, Public: 1}, rs.TierCounts)
	require.Equal(t, map[string]int{"api": 3, "db": 2}, rs.DomainCounts)
}

// TestRemoteStatsDecodesStoreStatsWireShape serves a body marshalled from
// the public StoreStats type and decodes it through the remote client,
// pinning the wire DTO to the StoreStats vocabulary so the two cannot drift.
func TestRemoteStatsDecodesStoreStatsWireShape(t *testing.T) {
	t.Parallel()
	body := StoreStats{
		TotalCount:   7,
		DomainCounts: map[string]int{"api": 4, "ci": 3},
		TierCounts:   map[Tier]int{Private: 6, Public: 1},
	}
	data, err := json.Marshal(body)
	require.NoError(t, err)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(data)
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	rs, statsErr := rc.stats(context.Background())
	require.NoError(t, statsErr)
	require.Equal(t, body.TotalCount, rs.TotalCount)
	require.Equal(t, body.TierCounts, rs.TierCounts)
	require.Equal(t, body.DomainCounts, rs.DomainCounts)
}

func TestRemoteStatsServerError(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	_, err := rc.stats(context.Background())
	require.ErrorIs(t, err, errUnreachable)
}

func TestRemoteStatsTransportError(t *testing.T) {
	t.Parallel()
	rc := newRemoteClient("http://127.0.0.1:1", "", 1*time.Second, staticResolver{})
	_, err := rc.stats(context.Background())
	require.ErrorIs(t, err, errUnreachable)
}

func TestRemoteQueryAddsPatternToURL(t *testing.T) {
	t.Parallel()

	var (
		mu          sync.Mutex
		capturedURL string
	)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		capturedURL = r.URL.String()
		mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"data":[]}`))
	}))
	t.Cleanup(srv.Close)

	rc := newRemoteClient(srv.URL, "test-key", 5*time.Second, staticResolver{})
	_, _ = rc.query(context.Background(), QueryParams{
		Domains: []string{"api"},
		Pattern: "api-client",
	})

	mu.Lock()
	defer mu.Unlock()
	require.Contains(t, capturedURL, "pattern=api-client")
}

func TestRemoteQueryOmitsEmptyPattern(t *testing.T) {
	t.Parallel()

	var (
		mu          sync.Mutex
		capturedURL string
	)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		capturedURL = r.URL.String()
		mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"data":[]}`))
	}))
	t.Cleanup(srv.Close)

	rc := newRemoteClient(srv.URL, "test-key", 5*time.Second, staticResolver{})
	_, _ = rc.query(context.Background(), QueryParams{Domains: []string{"api"}})

	mu.Lock()
	defer mu.Unlock()
	require.NotContains(t, capturedURL, "pattern=")
}

func TestRemoteRevokePostsToNamedAction(t *testing.T) {
	t.Parallel()

	const unitID = "ku_00000000000000000000000000000007"

	var mu sync.Mutex
	var gotMethod, gotPath string
	var gotBody map[string]any

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)

		mu.Lock()
		gotMethod, gotPath, gotBody = r.Method, r.URL.Path, body
		mu.Unlock()

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(testRemoteKUJSON(unitID))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	unit, err := rc.revoke(context.Background(), unitID)
	require.NoError(t, err)
	require.Equal(t, unitID, unit.ID)

	mu.Lock()
	defer mu.Unlock()
	require.Equal(t, http.MethodPost, gotMethod)
	require.Equal(t, "/api/v1/users/me/knowledge/"+unitID+"/revoke", gotPath)
	require.Empty(t, gotBody)
}

func TestRemoteRevokeNotFoundReturnsRemoteError(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"detail":"Knowledge unit not found."}`))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	_, err := rc.revoke(context.Background(), "ku_00000000000000000000000000000007")

	var remoteErr *RemoteError
	require.ErrorAs(t, err, &remoteErr)
	require.Equal(t, http.StatusNotFound, remoteErr.StatusCode)
}

func TestRemoteRevokeServerErrorIsUnreachable(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	_, err := rc.revoke(context.Background(), "ku_00000000000000000000000000000007")
	require.ErrorIs(t, err, errUnreachable)
}

func TestRemoteRevokeRejectsEmptySuccessBody(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name   string
		status int
	}{
		{name: "200 with empty body", status: http.StatusOK},
		{name: "204 no content", status: http.StatusNoContent},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(tc.status)
			}))
			defer srv.Close()

			rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
			_, err := rc.revoke(context.Background(), "ku_00000000000000000000000000000007")
			require.ErrorIs(t, err, errUnreachable)
		})
	}
}

func TestRemoteListRequestsOwnKnowledge(t *testing.T) {
	t.Parallel()

	var mu sync.Mutex
	var gotMethod, gotPath string
	var gotQuery url.Values

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		gotMethod, gotPath, gotQuery = r.Method, r.URL.Path, r.URL.Query()
		mu.Unlock()

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"data":[]}`))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	_, err := rc.list(context.Background(), ListParams{
		Cursor: "cursor_abc",
		Limit:  7,
		Status: Pending,
	})
	require.NoError(t, err)

	mu.Lock()
	defer mu.Unlock()
	require.Equal(t, http.MethodGet, gotMethod)
	require.Equal(t, "/api/v1/users/me/knowledge", gotPath)
	require.Equal(t, []string{"pending"}, gotQuery["status"])
	require.Equal(t, "7", gotQuery.Get("limit"))
	require.Equal(t, "cursor_abc", gotQuery.Get("cursor"))
}

func TestRemoteListOmitsEmptyFilters(t *testing.T) {
	t.Parallel()

	var mu sync.Mutex
	var gotRawQuery string

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		gotRawQuery = r.URL.RawQuery
		mu.Unlock()

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"data":[]}`))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	_, err := rc.list(context.Background(), ListParams{})
	require.NoError(t, err)

	mu.Lock()
	defer mu.Unlock()
	require.Empty(t, gotRawQuery)
}

func TestRemoteListPairsEachUnitWithItsStatus(t *testing.T) {
	t.Parallel()

	const unitID = "ku_00000000000000000000000000000008"

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"data": []map[string]any{testRemoteOwnUnitJSON(unitID, Pending)},
		})
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	result, err := rc.list(context.Background(), ListParams{})
	require.NoError(t, err)
	require.Len(t, result.Units, 1)
	require.Equal(t, unitID, result.Units[0].ID)
	require.Equal(t, Pending, result.Units[0].Status)
}

func TestRemoteListUnauthorizedReturnsRemoteError(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"detail":"API key expired."}`))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	_, err := rc.list(context.Background(), ListParams{})

	var remoteErr *RemoteError
	require.ErrorAs(t, err, &remoteErr)
	require.Equal(t, http.StatusUnauthorized, remoteErr.StatusCode)
}

func TestRemoteListServerErrorIsUnreachable(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	_, err := rc.list(context.Background(), ListParams{})
	require.ErrorIs(t, err, errUnreachable)
}

func TestRemoteListRejectsMissingDataField(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{}`))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	_, err := rc.list(context.Background(), ListParams{})
	require.ErrorContains(t, err, "missing or null data field")
}

func TestRemoteListReturnsNextCursor(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"data":[],"next_cursor":"cursor_next"}`))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	result, err := rc.list(context.Background(), ListParams{})
	require.NoError(t, err)
	require.Equal(t, "cursor_next", result.NextCursor)
}

func TestRemoteListEndOfStreamCarriesNoCursor(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"data":[],"next_cursor":null}`))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	result, err := rc.list(context.Background(), ListParams{})
	require.NoError(t, err)
	require.Empty(t, result.NextCursor)
}

func TestRemoteListSendsTagFilters(t *testing.T) {
	t.Parallel()

	var mu sync.Mutex
	var gotQuery url.Values

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		gotQuery = r.URL.Query()
		mu.Unlock()

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"data":[]}`))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	_, err := rc.list(context.Background(), ListParams{
		Domains:    []string{"api", "payments"},
		Frameworks: []string{"fastapi"},
		Languages:  []string{"go"},
		Pattern:    "shell-quoting",
		Search:     "nektos/act",
	})
	require.NoError(t, err)

	mu.Lock()
	defer mu.Unlock()
	// The member surface names each tag axis in the singular and repeats the
	// parameter per value, unlike the plural names the commons search takes.
	require.Equal(t, []string{"api", "payments"}, gotQuery["domain"])
	require.Equal(t, []string{"go"}, gotQuery["language"])
	require.Equal(t, []string{"fastapi"}, gotQuery["framework"])
	require.Equal(t, "shell-quoting", gotQuery.Get("pattern"))
	require.Equal(t, "nektos/act", gotQuery.Get("q"))
}

func TestRemoteListReturnsFacets(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(
			`{"data":[],"facets":{"domains":{"api":3},"languages":{"go":2},"frameworks":{"fastapi":1}}}`,
		))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second, staticResolver{})
	result, err := rc.list(context.Background(), ListParams{})
	require.NoError(t, err)
	require.Equal(t, map[string]int{"api": 3}, result.Facets.Domains)
	require.Equal(t, map[string]int{"go": 2}, result.Facets.Languages)
	require.Equal(t, map[string]int{"fastapi": 1}, result.Facets.Frameworks)
}
