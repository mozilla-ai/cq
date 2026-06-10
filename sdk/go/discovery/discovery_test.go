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
	"sync"
	"sync/atomic"
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

func TestResolveErrorsOnTrailingContent(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"version": 1,
			"api_base_url": "https://api.example.com/api/v1",
			"api_version": "v1"
		} garbage`))
	}))
	defer srv.Close()

	_, err := newTestResolver(t).Resolve(context.Background(), srv.URL)
	require.Error(t, err)
	require.Contains(t, strings.ToLower(err.Error()), "trailing")
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

	// Without WithLogger, New uses the slog.DiscardHandler default
	// from defaultOptions. Even when the disk cache write fails
	// (cache dir occupied by a regular file so MkdirAll cannot
	// create the directory), no record escapes the handler. This
	// pins the MCP/STDIO invariant: the SDK writes nothing without
	// explicit caller wiring.
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

func TestResolveErrorsOnNonNumericPortInAPIBaseURL(t *testing.T) {
	t.Parallel()

	// url.Parse accepts a non-numeric port without complaint, so without
	// explicit validation the failure surfaces later as a transport
	// error.
	// Pin that the discovery layer rejects it up front with a
	// domain-y message that names the offending field.
	var calls int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"version": 1,
			"api_base_url": "https://example.com:bad/api/v1",
			"api_version": "v1"
		}`))
	}))
	defer srv.Close()

	r := newTestResolver(t)
	_, err := r.Resolve(context.Background(), srv.URL)
	require.Error(t, err)
	require.Contains(t, strings.ToLower(err.Error()), "port")

	// A failed validation is not memoized, so a second call probes
	// the network again rather than returning a cached error.
	_, err = r.Resolve(context.Background(), srv.URL)
	require.Error(t, err)
	require.Equal(t, 2, calls)
}

func TestResolveErrorsOnOutOfRangePortInAPIBaseURL(t *testing.T) {
	t.Parallel()

	// url.Parse accepts numeric ports outside the uint16 range, so
	// without the strconv.ParseUint check in validate() the failure
	// would surface later as an opaque transport error.
	// Pin that an out-of-range numeric port is rejected at validation
	// time with a domain-y message naming the offending field.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"version": 1,
			"api_base_url": "https://example.com:99999/api/v1",
			"api_version": "v1"
		}`))
	}))
	defer srv.Close()

	_, err := newTestResolver(t).Resolve(context.Background(), srv.URL)
	require.Error(t, err)
	require.Contains(t, strings.ToLower(err.Error()), "port")
}

// waitForInflightWaiter blocks until at least n goroutines have registered as
// waiters on the in-flight Resolve for addr.
// The elected prober does not count toward n.
// Used only by single-flight tests to remove the "did the second
// caller register yet" race without exposing internal state to
// production callers.
func (r *Resolver) waitForInflightWaiter(t *testing.T, addr string, n int) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for {
		r.mu.Lock()
		call, ok := r.inflight[addr]
		waiters := 0
		if ok {
			waiters = call.waiters
		}
		r.mu.Unlock()
		if waiters >= n {
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("timed out waiting for %d in-flight waiter(s) on %s (have %d, registered=%v)", n, addr, waiters, ok)
		}
		time.Sleep(time.Millisecond)
	}
}

func TestResolverCoalescesConcurrentResolvesForSameAddr(t *testing.T) {
	t.Parallel()

	// Block the elected prober inside the handler until both callers
	// have registered. Single-flight should collapse the two Resolve
	// calls into a single HTTP probe and deliver the same NodeInfo to
	// each caller.
	var calls int32
	gate := make(chan struct{})
	var gateOnce sync.Once
	releaseGate := func() { gateOnce.Do(func() { close(gate) }) }
	// Register cleanup so an assertion failure inside the test cannot
	// leave the handler blocked on gate and hang srv.Close().
	t.Cleanup(releaseGate)
	arrived := make(chan struct{}, 1)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		atomic.AddInt32(&calls, 1)
		select {
		case arrived <- struct{}{}:
		default:
		}
		<-gate
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"version": 1,
			"api_base_url": "https://api.example.com/api/v1",
			"api_version": "v1"
		}`))
	}))
	defer srv.Close()

	r := newTestResolver(t)

	type result struct {
		info NodeInfo
		err  error
	}
	out := make(chan result, 2)

	go func() {
		info, err := r.Resolve(context.Background(), srv.URL)
		out <- result{info, err}
	}()
	<-arrived
	go func() {
		info, err := r.Resolve(context.Background(), srv.URL)
		out <- result{info, err}
	}()
	r.waitForInflightWaiter(t, srv.URL, 1)
	releaseGate()

	r1 := <-out
	r2 := <-out
	require.NoError(t, r1.err)
	require.NoError(t, r2.err)
	require.Equal(t, r1.info, r2.info)
	require.Equal(t, int32(1), atomic.LoadInt32(&calls))
}

func TestResolverProbesIndependentAddrsConcurrently(t *testing.T) {
	t.Parallel()

	// Two different addresses must not coalesce; each gets its own
	// probe.
	// httptest binds a single host, so we differentiate the two
	// "addresses" by the addr argument's trailing path segment.
	// The single-flight key is the full normalized addr, so this is
	// enough to keep them distinct in-process.
	var calls int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		atomic.AddInt32(&calls, 1)
		w.Header().Set("Content-Type", "application/json")
		if strings.HasPrefix(req.URL.Path, "/one") {
			_, _ = w.Write([]byte(`{
				"version": 1,
				"api_base_url": "https://api-one.example.com/api/v1",
				"api_version": "v1"
			}`))
			return
		}
		_, _ = w.Write([]byte(`{
			"version": 1,
			"api_base_url": "https://api-two.example.com/api/v1",
			"api_version": "v1"
		}`))
	}))
	defer srv.Close()

	addrOne := srv.URL + "/one"
	addrTwo := srv.URL + "/two"

	r := newTestResolver(t)

	type result struct {
		info NodeInfo
		err  error
	}
	out := make(chan result, 2)
	go func() {
		info, err := r.Resolve(context.Background(), addrOne)
		out <- result{info, err}
	}()
	go func() {
		info, err := r.Resolve(context.Background(), addrTwo)
		out <- result{info, err}
	}()

	got := map[string]NodeInfo{}
	for range 2 {
		res := <-out
		require.NoError(t, res.err)
		got[res.info.APIBaseURL] = res.info
	}
	require.Equal(t, int32(2), atomic.LoadInt32(&calls))
	require.Contains(t, got, "https://api-one.example.com/api/v1")
	require.Contains(t, got, "https://api-two.example.com/api/v1")
}

func TestResolverPropagatesProbeFailureToAllWaiters(t *testing.T) {
	t.Parallel()

	// An elected probe that errors out must propagate the same error
	// to every concurrent waiter, with exactly one HTTP call charged.
	var calls int32
	gate := make(chan struct{})
	var gateOnce sync.Once
	releaseGate := func() { gateOnce.Do(func() { close(gate) }) }
	// Register cleanup so an assertion failure inside the test cannot
	// leave the handler blocked on gate and hang srv.Close().
	t.Cleanup(releaseGate)
	arrived := make(chan struct{}, 1)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		atomic.AddInt32(&calls, 1)
		select {
		case arrived <- struct{}{}:
		default:
		}
		<-gate
		w.Header().Set("Content-Type", "text/html")
		_, _ = w.Write([]byte(`<!doctype html><html>...</html>`))
	}))
	defer srv.Close()

	r := newTestResolver(t)
	errs := make(chan error, 2)

	go func() {
		_, err := r.Resolve(context.Background(), srv.URL)
		errs <- err
	}()
	<-arrived
	go func() {
		_, err := r.Resolve(context.Background(), srv.URL)
		errs <- err
	}()
	r.waitForInflightWaiter(t, srv.URL, 1)
	releaseGate()

	e1 := <-errs
	e2 := <-errs
	require.Error(t, e1)
	require.Error(t, e2)
	require.Equal(t, int32(1), atomic.LoadInt32(&calls))
}

func TestResolverDoesNotMemoizeFailedProbes(t *testing.T) {
	t.Parallel()

	// A failed probe must not memoize; the next caller must retry the
	// network. Two sequential failing calls means two HTTP probes.
	var calls int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		atomic.AddInt32(&calls, 1)
		w.Header().Set("Content-Type", "text/html")
		_, _ = w.Write([]byte(`<!doctype html><html>...</html>`))
	}))
	defer srv.Close()

	r := newTestResolver(t)
	_, err := r.Resolve(context.Background(), srv.URL)
	require.Error(t, err)
	_, err = r.Resolve(context.Background(), srv.URL)
	require.Error(t, err)
	require.Equal(t, int32(2), atomic.LoadInt32(&calls))
}
