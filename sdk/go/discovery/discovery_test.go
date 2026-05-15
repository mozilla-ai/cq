package discovery

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func newTestResolver(t *testing.T) *Resolver {
	t.Helper()
	return New(t.TempDir(), &http.Client{Timeout: 2 * time.Second})
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

func TestResolverSkipsFileCacheWhenCacheDirEmpty(t *testing.T) {
	t.Parallel()

	var calls int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		http.NotFound(w, r)
	}))
	defer srv.Close()

	r := New("", &http.Client{Timeout: 2 * time.Second})
	_, err := r.Resolve(context.Background(), srv.URL)
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
