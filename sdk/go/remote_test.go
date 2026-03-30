package cq

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestRemoteQuery(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/query", r.URL.Path)
		require.Equal(t, "GET", r.Method)
		require.Equal(t, []string{"api", "testing"}, r.URL.Query()["domain"])

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode([]map[string]any{testRemoteKUJSON("ku_00000000000000000000000000000002")})
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second)
	units := rc.query(context.Background(), QueryParams{Domains: []string{"api", "testing"}})
	require.Len(t, units, 1)
	assert.Equal(t, "ku_00000000000000000000000000000002", units[0].ID)
	assert.Equal(t, "S", units[0].Insight.Summary)
}

func TestRemoteQueryWithAuth(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "Bearer test-token", r.Header.Get("Authorization"))
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode([]map[string]any{})
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "test-token", 5*time.Second)
	units := rc.query(context.Background(), QueryParams{Domains: []string{"api"}})
	require.Empty(t, units)
}

func TestRemoteQueryServerError(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second)
	units := rc.query(context.Background(), QueryParams{Domains: []string{"api"}})
	require.Nil(t, units)
}

func TestRemotePropose(t *testing.T) {
	t.Parallel()
	var received map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/propose", r.URL.Path)
		require.Equal(t, "POST", r.Method)
		_ = json.NewDecoder(r.Body).Decode(&received)

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(w).Encode(testRemoteKUJSON("ku_00000000000000000000000000000005"))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second)
	ku := KnowledgeUnit{
		Domains: []string{"api"},
		Insight: Insight{Summary: "S", Detail: "D", Action: "A"},
	}
	result, err := rc.propose(context.Background(), ku)
	require.NoError(t, err)
	assert.Equal(t, "ku_00000000000000000000000000000005", result.ID)
	assert.Equal(t, []any{"api"}, received["domains"])
}

func TestRemoteProposeRejected(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusUnprocessableEntity)
		_, _ = w.Write([]byte("validation failed"))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second)
	ku := KnowledgeUnit{Domains: []string{"api"}, Insight: Insight{Summary: "S", Detail: "D", Action: "A"}}
	_, err := rc.propose(context.Background(), ku)
	require.Error(t, err)

	var remoteErr *RemoteError
	require.ErrorAs(t, err, &remoteErr)
	assert.Equal(t, 422, remoteErr.StatusCode)
}

func TestRemoteConfirm(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/confirm/ku_00000000000000000000000000000005", r.URL.Path)
		require.Equal(t, "POST", r.Method)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(testRemoteKUJSON("ku_00000000000000000000000000000005"))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second)
	ku, err := rc.confirm(context.Background(), "ku_00000000000000000000000000000005")
	require.NoError(t, err)
	assert.Equal(t, "ku_00000000000000000000000000000005", ku.ID)
}

func TestRemoteFlag(t *testing.T) {
	t.Parallel()
	var received map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/flag/ku_00000000000000000000000000000005", r.URL.Path)
		_ = json.NewDecoder(r.Body).Decode(&received)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(testRemoteKUJSON("ku_00000000000000000000000000000005"))
	}))
	defer srv.Close()

	rc := newRemoteClient(srv.URL, "", 5*time.Second)
	ku, err := rc.flag(context.Background(), "ku_00000000000000000000000000000005", Stale, flagConfig{})
	require.NoError(t, err)
	require.NotNil(t, ku)
	assert.Equal(t, "stale", received["reason"])
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

	rc := newRemoteClient(srv.URL, "", 5*time.Second)
	cfg := flagConfig{detail: "it is old", duplicateOf: "ku_00000000000000000000000000000002"}
	_, err := rc.flag(context.Background(), "ku_00000000000000000000000000000005", Duplicate, cfg)
	require.NoError(t, err)
	assert.Equal(t, "duplicate", received["reason"])
	assert.Equal(t, "it is old", received["detail"])
	assert.Equal(t, "ku_00000000000000000000000000000002", received["duplicate_of"])
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

	rc := newRemoteClient(srv.URL, "", 5*time.Second)
	_, err := rc.flag(context.Background(), "ku_00000000000000000000000000000005", Stale, flagConfig{})
	require.NoError(t, err)
	_, hasDetail := received["detail"]
	_, hasDup := received["duplicate_of"]
	assert.False(t, hasDetail, "empty detail should not be sent")
	assert.False(t, hasDup, "empty duplicate_of should not be sent")
}
