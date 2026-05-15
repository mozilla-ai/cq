package auth

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestClient_CreateAPIKey_SuccessReturnsTokenAndMetadata(t *testing.T) {
	cap := newCapture()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cap.recordRequest(r)

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		_, _ = w.Write([]byte(`{
			"id": "00000000-0000-0000-0000-000000000001",
			"name": "claude-cursor",
			"labels": ["ci","laptop"],
			"key_prefix": "cqa12345",
			"ttl": "30d",
			"expires_at": "2026-06-08T12:00:00Z",
			"created_at": "2026-05-08T12:00:00Z",
			"last_used_at": null,
			"revoked_at": null,
			"is_expired": false,
			"is_active": true,
			"api_key": "cqa.v1.0123456789abcdef0123456789abcdef.secret-secret-secret-secret-secret-secret-12345678"
		}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	got, err := client.CreateAPIKey(context.Background(), "test-jwt", CreateAPIKeyRequest{
		Name:   "claude-cursor",
		TTL:    "30d",
		Labels: []string{"ci", "laptop"},
	})
	require.NoError(t, err)
	require.Equal(t, "claude-cursor", got.Name)
	require.Equal(t, []string{"ci", "laptop"}, got.Labels)
	require.Equal(t, "cqa12345", got.Prefix)
	require.True(t, got.IsActive)
	require.False(t, got.IsExpired)
	require.NotEmpty(t, got.Token)

	c := cap.snapshot()
	require.Equal(t, http.MethodPost, c.method)
	require.Equal(t, "/api/v1/users/me/api-keys", c.path)
	require.Equal(t, "Bearer test-jwt", c.auth)

	var body map[string]any
	require.NoError(t, json.Unmarshal(c.body, &body))
	require.Equal(t, "claude-cursor", body["name"])
	require.Equal(t, "30d", body["ttl"])
	require.ElementsMatch(t, []any{"ci", "laptop"}, body["labels"])
}

func TestClient_CreateAPIKey_SessionExpired_ReturnsSentinel(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"detail":"Not authenticated"}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	_, err := client.CreateAPIKey(context.Background(), "stale", CreateAPIKeyRequest{Name: "x", TTL: "30d"})
	require.ErrorIs(t, err, ErrSessionExpired)
}

func TestClient_CreateAPIKey_LimitReached_ReturnsTypedError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusConflict)
		_, _ = w.Write([]byte(`{"detail":"Maximum of 20 active API keys per user"}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	_, err := client.CreateAPIKey(context.Background(), "jwt", CreateAPIKeyRequest{Name: "x", TTL: "30d"})

	var capReached *APIKeyLimitReachedError
	require.ErrorAs(t, err, &capReached)
	require.Contains(t, capReached.Detail, "Maximum of 20")
}

func TestClient_CreateAPIKey_InvalidTTL_ReturnsValidationError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusUnprocessableEntity)
		_, _ = w.Write([]byte(`{"detail":"TTL must match ^\\d+[smhd]$"}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	_, err := client.CreateAPIKey(context.Background(), "jwt", CreateAPIKeyRequest{Name: "x", TTL: "1w"})

	var validation *APIKeyValidationError
	require.ErrorAs(t, err, &validation)
	require.Contains(t, validation.Detail, "TTL must match")
}

func TestClient_ListAPIKeys_DecodesEnvelope(t *testing.T) {
	cap := newCapture()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cap.recordRequest(r)

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"data": [
				{
					"id": "id-a",
					"name": "alpha",
					"labels": [],
					"key_prefix": "cqaAAAA",
					"ttl": "30d",
					"expires_at": "2026-06-08T00:00:00Z",
					"created_at": "2026-05-08T00:00:00Z",
					"last_used_at": null,
					"revoked_at": null,
					"is_expired": false,
					"is_active": true
				},
				{
					"id": "id-b",
					"name": "beta",
					"labels": ["ci"],
					"key_prefix": "cqaBBBB",
					"ttl": "1d",
					"expires_at": "2026-05-09T00:00:00Z",
					"created_at": "2026-05-08T00:00:00Z",
					"last_used_at": "2026-05-08T01:00:00Z",
					"revoked_at": "2026-05-08T02:00:00Z",
					"is_expired": false,
					"is_active": false
				}
			],
			"count": 2
		}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	got, err := client.ListAPIKeys(context.Background(), "jwt")
	require.NoError(t, err)
	require.Len(t, got, 2)
	require.Equal(t, "alpha", got[0].Name)
	require.True(t, got[0].IsActive)
	require.Equal(t, "beta", got[1].Name)
	require.False(t, got[1].IsActive)
	require.NotNil(t, got[1].RevokedAt)
	require.Equal(t, time.Date(2026, 5, 8, 2, 0, 0, 0, time.UTC), got[1].RevokedAt.UTC())

	c := cap.snapshot()
	require.Equal(t, http.MethodGet, c.method)
	require.Equal(t, "/api/v1/users/me/api-keys", c.path)
}

func TestClient_ListAPIKeys_SessionExpired_ReturnsSentinel(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"detail":"Not authenticated"}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	_, err := client.ListAPIKeys(context.Background(), "stale")
	require.ErrorIs(t, err, ErrSessionExpired)
}

func TestClient_RevokeAPIKey_SuccessReturnsNoError(t *testing.T) {
	cap := newCapture()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cap.recordRequest(r)

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"message":"API key revoked."}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	require.NoError(t, client.RevokeAPIKey(context.Background(), "jwt", "key-123"))

	c := cap.snapshot()
	require.Equal(t, http.MethodPost, c.method)
	require.Equal(t, "/api/v1/users/me/api-keys/key-123/revoke", c.path)
	require.Equal(t, "Bearer jwt", c.auth)
}

func TestClient_RevokeAPIKey_PathEscapesKeyID(t *testing.T) {
	var rawPath string
	var mu sync.Mutex

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		rawPath = r.URL.EscapedPath()
		mu.Unlock()

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"message":"API key revoked."}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	// A pathological keyID with characters the URL grammar reserves;
	// the client must escape it rather than splice it raw into the URL.
	require.NoError(t, client.RevokeAPIKey(context.Background(), "jwt", "weird/key id"))

	mu.Lock()
	defer mu.Unlock()
	require.Equal(t, "/api/v1/users/me/api-keys/weird%2Fkey%20id/revoke", rawPath)
}

func TestClient_RevokeAPIKey_NotFoundReturnsTypedErrorWithKeyID(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"detail":"API key not found"}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	err := client.RevokeAPIKey(context.Background(), "jwt", "missing-id")

	var notFound *APIKeyNotFoundError
	require.ErrorAs(t, err, &notFound)
	require.Equal(t, "missing-id", notFound.KeyID)
}

func TestClient_RevokeAPIKey_SessionExpired_ReturnsSentinel(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"detail":"Not authenticated"}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	require.ErrorIs(t, client.RevokeAPIKey(context.Background(), "stale", "any"), ErrSessionExpired)
}
