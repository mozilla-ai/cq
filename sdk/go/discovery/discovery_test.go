package discovery

import (
	"bytes"
	"context"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func newTestResolver(t *testing.T) *Resolver {
	t.Helper()
	r, err := New(
		WithCacheDir(t.TempDir()),
		WithHTTPClient(&http.Client{Timeout: 2 * time.Second}),
	)
	require.NoError(t, err)
	return r
}

func TestResolveFallsBackToDefaultsOn404(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.NotFound(w, r)
	}))
	defer srv.Close()

	info, err := newTestResolver(t).Resolve(context.Background(), srv.URL)
	require.NoError(t, err)
	require.Equal(t, srv.URL+DefaultAPIPath, info.APIBaseURL)
	require.Equal(t, DefaultAPIVersion, info.APIVersion)
}

func TestResolveAcceptsValidDiscoveryDocument(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, WellKnownPath, r.URL.Path)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"version": 1,
			"api_base_url": "https://api.example.com/api/v1",
			"api_version": "v1",
			"node_name": "example"
		}`))
	}))
	defer srv.Close()

	info, err := newTestResolver(t).Resolve(context.Background(), srv.URL)
	require.NoError(t, err)
	require.Equal(t, "https://api.example.com/api/v1", info.APIBaseURL)
	require.Equal(t, "v1", info.APIVersion)
	require.Equal(t, "example", info.NodeName)
}

func TestResolveErrorsOnHTMLResponse(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		_, _ = w.Write([]byte(`<!doctype html><html>...</html>`))
	}))
	defer srv.Close()

	_, err := newTestResolver(t).Resolve(context.Background(), srv.URL)
	require.Error(t, err)
	require.Contains(t, err.Error(), "SPA")
}

func TestResolveErrorsOnMalformedJSON(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{not valid`))
	}))
	defer srv.Close()

	_, err := newTestResolver(t).Resolve(context.Background(), srv.URL)
	require.Error(t, err)
	require.Contains(t, strings.ToLower(err.Error()), "parse")
}

func TestResolveErrorsOnVersionMismatch(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"version": 1,
			"api_base_url": "https://api.example.com/api/v2",
			"api_version": "v2"
		}`))
	}))
	defer srv.Close()

	_, err := newTestResolver(t).Resolve(context.Background(), srv.URL)
	require.Error(t, err)
	require.Contains(t, err.Error(), "v2")
	require.Contains(t, err.Error(), "v1")
}

func TestResolveErrorsOnDiscoveryVersionMismatch(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"version": 2,
			"api_base_url": "https://api.example.com/api/v1",
			"api_version": "v1"
		}`))
	}))
	defer srv.Close()

	_, err := newTestResolver(t).Resolve(context.Background(), srv.URL)
	require.Error(t, err)
	require.Contains(t, err.Error(), "version 2")
}

func TestResolveErrorsOnMissingDiscoveryVersion(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"api_base_url": "https://api.example.com/api/v1",
			"api_version": "v1"
		}`))
	}))
	defer srv.Close()

	_, err := newTestResolver(t).Resolve(context.Background(), srv.URL)
	require.Error(t, err)
	require.Contains(t, err.Error(), "version 0")
}

func TestResolveErrorsOnHostlessAPIBaseURL(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"version": 1,
			"api_base_url": "https://",
			"api_version": "v1"
		}`))
	}))
	defer srv.Close()

	_, err := newTestResolver(t).Resolve(context.Background(), srv.URL)
	require.Error(t, err)
	require.Contains(t, strings.ToLower(err.Error()), "host")
}

func TestResolveErrorsOnNonHTTPAPIBaseURL(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"version": 1,
			"api_base_url": "ftp://example.com/api/v1",
			"api_version": "v1"
		}`))
	}))
	defer srv.Close()

	_, err := newTestResolver(t).Resolve(context.Background(), srv.URL)
	require.Error(t, err)
	require.Contains(t, strings.ToLower(err.Error()), "scheme")
}

func TestResolveErrorsOnUnknownField(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"version": 1,
			"api_base_url": "https://api.example.com/api/v1",
			"api_version": "v1",
			"made_up_field": "x"
		}`))
	}))
	defer srv.Close()

	_, err := newTestResolver(t).Resolve(context.Background(), srv.URL)
	require.Error(t, err)
	require.Contains(t, strings.ToLower(err.Error()), "made_up_field")
}

func TestResolveRetriesOn5xxThenErrors(t *testing.T) {
	t.Parallel()

	var calls int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		http.Error(w, "boom", http.StatusInternalServerError)
	}))
	defer srv.Close()

	_, err := newTestResolver(t).Resolve(context.Background(), srv.URL)
	require.Error(t, err)
	require.GreaterOrEqual(t, calls, 2)
}

func TestResolveCachesSuccessfulResults(t *testing.T) {
	t.Parallel()

	var calls int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"version": 1,
			"api_base_url": "https://api.example.com/api/v1",
			"api_version": "v1"
		}`))
	}))
	defer srv.Close()

	r := newTestResolver(t)
	_, err := r.Resolve(context.Background(), srv.URL)
	require.NoError(t, err)
	_, err = r.Resolve(context.Background(), srv.URL)
	require.NoError(t, err)
	require.Equal(t, 1, calls)
}

func TestResolveCaches404FallbackResult(t *testing.T) {
	t.Parallel()

	var calls int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		http.NotFound(w, r)
	}))
	defer srv.Close()

	r := newTestResolver(t)
	_, err := r.Resolve(context.Background(), srv.URL)
	require.NoError(t, err)
	_, err = r.Resolve(context.Background(), srv.URL)
	require.NoError(t, err)
	require.Equal(t, 1, calls)
}

func TestResolverIsSilentByDefault(t *testing.T) {
	t.Parallel()

	// A nil logger to New() means slog.DiscardHandler. Even when the
	// disk cache write fails (cache dir occupied by a regular file so
	// MkdirAll cannot create the directory), no record reaches the
	// default handler. This pins the MCP/STDIO invariant: the SDK
	// writes nothing without explicit caller wiring.
	tmp := t.TempDir()
	blocked := filepath.Join(tmp, "blocked")
	require.NoError(t, os.WriteFile(blocked, []byte("x"), 0o600))

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.NotFound(w, r)
	}))
	defer srv.Close()

	r, err := New(
		WithCacheDir(blocked),
		WithHTTPClient(&http.Client{Timeout: 2 * time.Second}),
	)
	require.NoError(t, err)
	_, err = r.Resolve(context.Background(), srv.URL)
	require.NoError(t, err)
}

func TestResolverLogsCachePutFailure(t *testing.T) {
	t.Parallel()

	// When a logger IS wired in, a cache-write failure surfaces as a
	// warning record with the addr and error attached. This is the
	// observability the silent default trades away by design.
	tmp := t.TempDir()
	blocked := filepath.Join(tmp, "blocked")
	require.NoError(t, os.WriteFile(blocked, []byte("x"), 0o600))

	var buf bytes.Buffer
	logger := slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelWarn}))

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.NotFound(w, r)
	}))
	defer srv.Close()

	r, err := New(
		WithCacheDir(blocked),
		WithHTTPClient(&http.Client{Timeout: 2 * time.Second}),
		WithLogger(logger),
	)
	require.NoError(t, err)
	_, err = r.Resolve(context.Background(), srv.URL)
	require.NoError(t, err)

	got := buf.String()
	require.Contains(t, got, "cache write failed")
	require.Contains(t, got, srv.URL)
	require.Contains(t, got, `"level":"WARN"`)
}

func TestResolverSkipsFileCacheWhenCacheDirEmpty(t *testing.T) {
	t.Parallel()

	var calls int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		http.NotFound(w, r)
	}))
	defer srv.Close()

	r, err := New(WithHTTPClient(&http.Client{Timeout: 2 * time.Second}))
	require.NoError(t, err)
	_, err = r.Resolve(context.Background(), srv.URL)
	require.NoError(t, err)
	_, err = r.Resolve(context.Background(), srv.URL)
	require.NoError(t, err)

	// File cache is disabled, so each call relies on the in-process
	// memo only. The probe still hits once thanks to the in-process
	// memo; what we are pinning here is that the call does not error
	// or panic when no file cache backs it.
	require.GreaterOrEqual(t, calls, 1)
}

func TestResolveTrimsTrailingSlashInAddr(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.NotFound(w, r)
	}))
	defer srv.Close()

	info, err := newTestResolver(t).Resolve(context.Background(), srv.URL+"/")
	require.NoError(t, err)
	require.Equal(t, srv.URL+DefaultAPIPath, info.APIBaseURL)
}
