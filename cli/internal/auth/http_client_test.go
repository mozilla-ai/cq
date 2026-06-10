package auth

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
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

// newTestClient returns an httpClient pointed at serverURL with a
// staticResolver, bypassing real discovery so existing /api/v1/...
// path assertions hold without touching disk or network.
func newTestClient(serverURL string) Client {
	return &httpClient{
		addr:     serverURL,
		http:     &http.Client{Timeout: httpDefaultTimeout},
		resolver: staticResolver{},
	}
}

// TestHTTPClientResolvesAPIBaseURLViaDiscovery pins the default-on-404
// contract: when a node has no discovery document, the client must
// still hit {addr}/api/v1/<resource>. It exercises the real Resolver to
// catch regressions in the wiring between NewClient and the discovery
// package.
func TestHTTPClientResolvesAPIBaseURLViaDiscovery(t *testing.T) {
	var capturedPath string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == discovery.WellKnownPath {
			http.NotFound(w, r)
			return
		}
		capturedPath = r.URL.Path

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"providers": []}`))
	}))
	t.Cleanup(server.Close)

	client := NewClient(server.URL).(*httpClient)
	resolver, err := discovery.New(discovery.WithCacheDir(t.TempDir()))
	require.NoError(t, err)
	client.resolver = resolver

	_, err = client.OAuthProviders(context.Background())
	require.NoError(t, err)
	require.Equal(t, "/api/v1/oauth/providers", capturedPath)
}

// captured holds request data captured by a test server. Both ends are
// guarded by the embedded mutex; tests must Lock when reading.
type captured struct {
	sync.Mutex
	method string
	path   string
	query  string
	auth   string
	body   []byte
}

func newCapture() *captured {
	return &captured{}
}

// recordRequest reads r and stores the request method, path,
// Authorization header and body for later assertion.
func (c *captured) recordRequest(r *http.Request) {
	body, _ := io.ReadAll(r.Body)

	c.Lock()
	defer c.Unlock()

	c.method = r.Method
	c.path = r.URL.Path
	c.query = r.URL.RawQuery
	c.auth = r.Header.Get("Authorization")
	c.body = body
}

// snapshot returns a copy of the captured state, safe for use after the
// test server has closed.
func (c *captured) snapshot() captured {
	c.Lock()
	defer c.Unlock()

	return captured{method: c.method, path: c.path, query: c.query, auth: c.auth, body: c.body}
}

func TestClient_OAuthProviders_ReturnsEnabledProviders(t *testing.T) {
	cap := newCapture()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cap.recordRequest(r)

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(
			[]byte(
				`{"providers":[{"name":"github","display_name":"GitHub","enabled":true},{"name":"google","display_name":"Google","enabled":false}]}`,
			),
		)
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)

	got, err := client.OAuthProviders(context.Background())
	require.NoError(t, err)
	require.Equal(t, []Provider{
		{Name: "github", DisplayName: "GitHub", Enabled: true},
		{Name: "google", DisplayName: "Google", Enabled: false},
	}, got)

	c := cap.snapshot()
	require.Equal(t, http.MethodGet, c.method)
	require.Equal(t, "/api/v1/oauth/providers", c.path)
}

func TestClient_OAuthProviders_PropagatesHTTPError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "boom", http.StatusInternalServerError)
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)

	_, err := client.OAuthProviders(context.Background())
	require.Error(t, err)
}

func TestClient_OAuthProviders_NormalisesNameOnTheWayOut(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		// Mixed case + surrounding whitespace on Name; DisplayName is
		// left as the platform sent it.
		_, _ = w.Write([]byte(`{"providers":[{"name":"  GitHub  ","display_name":"GitHub","enabled":true}]}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)

	got, err := client.OAuthProviders(context.Background())
	require.NoError(t, err)
	require.Len(t, got, 1)
	require.Equal(t, "github", got[0].Name)
	require.Equal(t, "GitHub", got[0].DisplayName)
}

func TestClient_OAuthNativeStart_PostsCorrectBodyAndReturnsAuthorizationURL(t *testing.T) {
	cap := newCapture()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cap.recordRequest(r)

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"authorization_url":"https://provider.example/authorize?state=abc"}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	got, err := client.OAuthNativeStart(context.Background(), NativeStartRequest{
		Provider:      "github",
		CodeChallenge: "challenge-43-chars-abcdefghijklmnopqrstuv",
		RedirectURI:   "http://127.0.0.1:54321/cb",
	})
	require.NoError(t, err)
	require.Equal(t, "https://provider.example/authorize?state=abc", got)

	c := cap.snapshot()
	require.Equal(t, http.MethodPost, c.method)
	require.Equal(t, "/api/v1/oauth/native/start", c.path)

	var body map[string]any
	require.NoError(t, json.Unmarshal(c.body, &body))
	require.Equal(t, "github", body["provider"])
	require.Equal(t, "challenge-43-chars-abcdefghijklmnopqrstuv", body["code_challenge"])
	require.Equal(t, "http://127.0.0.1:54321/cb", body["redirect_uri"])
}

func TestClient_OAuthNativeStart_RateLimitedReturnsTypedErrorWithRetryAfter(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Retry-After", "42")
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	_, err := client.OAuthNativeStart(context.Background(), NativeStartRequest{
		Provider:      "github",
		CodeChallenge: "any",
		RedirectURI:   "any",
	})

	var rateErr *RateLimitedError
	require.ErrorAs(t, err, &rateErr)
	require.Equal(t, 42*time.Second, rateErr.RetryAfter)
}

func TestClient_OAuthNativeExchange_PostsCorrectBodyAndReturnsAccessToken(t *testing.T) {
	cap := newCapture()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cap.recordRequest(r)

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"access_token":"jwt-token"}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	got, err := client.OAuthNativeExchange(context.Background(), NativeExchangeRequest{
		ExchangeCode: "exchange-code-43-chars-aaaaaaaaaaaaaaaaaaaa",
		CodeVerifier: "verifier-value-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	})
	require.NoError(t, err)
	require.Equal(t, "jwt-token", got)

	c := cap.snapshot()
	require.Equal(t, http.MethodPost, c.method)
	require.Equal(t, "/api/v1/oauth/native/exchange", c.path)

	var body map[string]any
	require.NoError(t, json.Unmarshal(c.body, &body))
	require.Equal(t, "exchange-code-43-chars-aaaaaaaaaaaaaaaaaaaa", body["exchange_code"])
	require.Equal(t, "verifier-value-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", body["code_verifier"])
}

func TestClient_OAuthNativeExchange_InvalidGrantReturnsTypedError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte(`{"detail":"invalid_grant"}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	_, err := client.OAuthNativeExchange(
		context.Background(),
		NativeExchangeRequest{ExchangeCode: "x", CodeVerifier: "y"},
	)
	require.ErrorIs(t, err, ErrInvalidGrant)
}

func TestClient_Me_SendsBearerAndParsesUser(t *testing.T) {
	cap := newCapture()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cap.recordRequest(r)

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"id": "00000000-0000-0000-0000-000000000001",
			"email": "alice@example.com",
			"full_name": "Alice Example",
			"username": "alice",
			"oauth_provider": "github"
		}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	got, err := client.Me(context.Background(), "test-jwt")
	require.NoError(t, err)
	require.Equal(t, User{
		ID:            "00000000-0000-0000-0000-000000000001",
		Email:         "alice@example.com",
		FullName:      "Alice Example",
		Username:      "alice",
		OAuthProvider: "github",
	}, got)

	c := cap.snapshot()
	require.Equal(t, http.MethodGet, c.method)
	require.Equal(t, "/api/v1/users/me", c.path)
	require.Equal(t, "Bearer test-jwt", c.auth)
}

func TestClient_Me_HandlesNullableUsernameAndProvider(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"id": "id",
			"email": "x@y",
			"full_name": "N",
			"username": null,
			"oauth_provider": null
		}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	got, err := client.Me(context.Background(), "jwt")
	require.NoError(t, err)
	require.Empty(t, got.Username)
	require.Empty(t, got.OAuthProvider)
}

func TestClient_ClaimUsername_SuccessReturnsUser(t *testing.T) {
	cap := newCapture()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cap.recordRequest(r)

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"id": "id",
			"email": "x@y",
			"full_name": "N",
			"username": "alice",
			"oauth_provider": "github"
		}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	got, err := client.ClaimUsername(context.Background(), "jwt", "alice")
	require.NoError(t, err)
	require.Equal(t, "alice", got.Username)

	c := cap.snapshot()
	require.Equal(t, http.MethodPost, c.method)
	require.Equal(t, "/api/v1/users/me/username", c.path)
	require.Equal(t, "Bearer jwt", c.auth)

	var body map[string]any
	require.NoError(t, json.Unmarshal(c.body, &body))
	require.Equal(t, "alice", body["username"])
}

func TestClient_ClaimUsername_UnavailableReturnsTypedErrorWithSuggestions(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusConflict)
		_, _ = w.Write([]byte(`{"error":"username_unavailable","suggestions":["alice1","alice_dev"]}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	_, err := client.ClaimUsername(context.Background(), "jwt", "alice")

	var unavail *UsernameUnavailableError
	require.ErrorAs(t, err, &unavail)
	require.Equal(t, []string{"alice1", "alice_dev"}, unavail.Suggestions)
}

func TestClient_ClaimUsername_AlreadySetReturnsSentinel(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusConflict)
		_, _ = w.Write([]byte(`{"error":"username_already_set"}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	_, err := client.ClaimUsername(context.Background(), "jwt", "alice")
	require.ErrorIs(t, err, ErrUsernameAlreadySet)
}

func TestClient_ClaimUsername_InvalidFormatReturnsTypedErrorWithDetail(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusUnprocessableEntity)
		_, _ = w.Write([]byte(`{"error":"username_invalid_format","detail":"must start with a letter"}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	_, err := client.ClaimUsername(context.Background(), "jwt", "1bad")

	var formatErr *UsernameFormatError
	require.ErrorAs(t, err, &formatErr)
	require.Equal(t, "must start with a letter", formatErr.Detail)
}

func TestClient_ClaimUsername_RateLimitedReturnsTypedErrorWithRetryAfter(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Retry-After", "60")
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusTooManyRequests)
		_, _ = w.Write([]byte(`{"error":"username_rate_limited"}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	_, err := client.ClaimUsername(context.Background(), "jwt", "alice")

	var rateErr *RateLimitedError
	require.ErrorAs(t, err, &rateErr)
	require.Equal(t, 60*time.Second, rateErr.RetryAfter)
}

func TestClient_ClaimUsername_OtherErrorReturnsGenericError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "boom", http.StatusInternalServerError)
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	_, err := client.ClaimUsername(context.Background(), "jwt", "alice")
	require.Error(t, err)

	// Sanity: not one of the typed errors.
	require.False(t, errors.Is(err, ErrUsernameAlreadySet))

	var unavail *UsernameUnavailableError
	require.False(t, errors.As(err, &unavail))
}

func TestClient_Logout_PostsToAuthLogout(t *testing.T) {
	cap := newCapture()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cap.recordRequest(r)
		w.WriteHeader(http.StatusNoContent)
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	err := client.Logout(context.Background(), "jwt-token", false)
	require.NoError(t, err)

	c := cap.snapshot()
	require.Equal(t, http.MethodPost, c.method)
	require.Equal(t, "/api/v1/auth/logout", c.path)
	require.Equal(t, "Bearer jwt-token", c.auth)
}

func TestClient_Logout_AllDevicesAddsQueryParam(t *testing.T) {
	cap := newCapture()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cap.recordRequest(r)
		w.WriteHeader(http.StatusNoContent)
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	err := client.Logout(context.Background(), "jwt-token", true)
	require.NoError(t, err)

	c := cap.snapshot()
	require.Equal(t, "/api/v1/auth/logout", c.path)
	require.Equal(t, "all_devices=true", c.query)
}

func TestClient_Logout_UnsupportedEndpointReturnsTypedError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"detail":"Not Found"}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	err := client.Logout(context.Background(), "jwt-token", false)
	require.ErrorIs(t, err, ErrLogoutUnsupported)
}

func TestClient_Logout_ExpiredSessionReturnsErrSessionExpired(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"detail":"Invalid or expired token"}`))
	}))
	t.Cleanup(server.Close)

	client := newTestClient(server.URL)
	err := client.Logout(context.Background(), "jwt-token", false)
	require.ErrorIs(t, err, ErrSessionExpired)
}
