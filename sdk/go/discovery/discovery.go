package discovery

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

// Resolver maps a user-supplied cq node address to a NodeInfo by probing
// the node's discovery document at WellKnownPath. Results are memoized
// in-process for the lifetime of the Resolver, and persisted to disk so
// short-lived processes can share resolutions across invocations.
//
// Behavior:
//
//   - 404 from the discovery endpoint: returns defaults
//     (addr + DefaultAPIPath, DefaultAPIVersion). Cached.
//   - 200 with a valid document whose api_version matches
//     SupportedAPIVersion: parsed NodeInfo. Cached.
//   - 200 with text/html: error (the address likely points at a SPA,
//     not a cq node). Not cached.
//   - 200 with malformed JSON: error. Not cached.
//   - 200 with valid JSON but api_version mismatch: error with both
//     versions named so the user can act on the mismatch.
//   - 5xx, network error, timeout: retried once with a short backoff,
//     then error. Not cached.
//
// NOTE: callers should not share a Resolver across goroutines they
// don't control — the in-process memo is guarded by a mutex but
// concurrent callers will still race on the underlying HTTP probe.
type Resolver struct {
	fileCache *cache
	httpc     *http.Client

	mu       sync.Mutex
	memCache map[string]NodeInfo
}

// New constructs a Resolver that persists its cache under cacheDir.
// httpc may be nil, in which case a default with a short timeout is used.
// NOTE: cacheDir is created on first successful write; callers do not
// need to MkdirAll ahead of time.
func New(cacheDir string, httpc *http.Client) *Resolver {
	if httpc == nil {
		httpc = &http.Client{Timeout: 5 * time.Second}
	}
	return &Resolver{
		fileCache: newCache(cacheDir, DefaultCacheTTL),
		httpc:     httpc,
		memCache:  map[string]NodeInfo{},
	}
}

// Resolve returns the NodeInfo for addr. addr should be the user-facing
// origin; trailing slashes are normalized away. See Resolver for the
// full behavior contract.
func (r *Resolver) Resolve(ctx context.Context, addr string) (NodeInfo, error) {
	addr = strings.TrimRight(addr, "/")

	r.mu.Lock()
	if info, ok := r.memCache[addr]; ok {
		r.mu.Unlock()
		return info, nil
	}
	r.mu.Unlock()

	if info, ok := r.fileCache.get(addr); ok {
		r.cacheInMemory(addr, info)
		return info, nil
	}

	info, err := r.probe(ctx, addr)
	if err != nil {
		return NodeInfo{}, err
	}

	if err := r.fileCache.put(addr, info); err != nil {
		// Disk cache failure is non-fatal: the resolution itself is
		// valid for the lifetime of this process.
		_ = err
	}
	r.cacheInMemory(addr, info)
	return info, nil
}

// cacheInMemory records the resolution for addr in the in-process memo
// so subsequent Resolve calls within this process skip the disk read and
// the HTTP probe entirely.
func (r *Resolver) cacheInMemory(addr string, info NodeInfo) {
	r.mu.Lock()
	r.memCache[addr] = info
	r.mu.Unlock()
}

// probe fetches the discovery document for addr and turns it into a
// NodeInfo. A 404 yields the documented defaults so a node that has not
// published a discovery document still resolves cleanly. Any other
// non-2xx status, an HTML body, malformed JSON, or a version mismatch
// becomes an error so the caller can surface the underlying problem
// instead of silently falling back.
func (r *Resolver) probe(ctx context.Context, addr string) (NodeInfo, error) {
	u, err := url.JoinPath(addr, WellKnownPath)
	if err != nil {
		return NodeInfo{}, fmt.Errorf("build discovery URL: %w", err)
	}

	resp, err := r.fetchWithRetry(ctx, u, 2)
	if err != nil {
		return NodeInfo{}, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return defaultsFor(addr), nil
	}
	if resp.StatusCode != http.StatusOK {
		return NodeInfo{}, fmt.Errorf("discovery: unexpected status %d from %s", resp.StatusCode, u)
	}

	ct := resp.Header.Get("Content-Type")
	if strings.HasPrefix(ct, "text/html") {
		return NodeInfo{}, fmt.Errorf("discovery: %s returned text/html — the address likely points at a SPA, not a cq node API", addr)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, 64<<10))
	if err != nil {
		return NodeInfo{}, fmt.Errorf("discovery: read body: %w", err)
	}

	var info NodeInfo
	if err := json.Unmarshal(body, &info); err != nil {
		return NodeInfo{}, fmt.Errorf("discovery: parse body: %w", err)
	}

	if err := validate(info); err != nil {
		return NodeInfo{}, fmt.Errorf("discovery: %w", err)
	}
	return info, nil
}

// fetchWithRetry issues a GET to u and retries up to attempts times on
// transport errors and 5xx responses, with a short linear backoff
// between attempts. A 4xx response is returned to the caller without
// retry so probe can distinguish 404 (a documented success case) from
// genuine transient failures.
// NOTE: callers must close the returned response body.
func (r *Resolver) fetchWithRetry(ctx context.Context, u string, attempts int) (*http.Response, error) {
	var lastErr error
	for i := 0; i < attempts; i++ {
		if i > 0 {
			select {
			case <-ctx.Done():
				return nil, ctx.Err()
			case <-time.After(time.Duration(i) * 200 * time.Millisecond):
			}
		}
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
		if err != nil {
			return nil, err
		}
		req.Header.Set("Accept", "application/json")
		resp, err := r.httpc.Do(req)
		if err != nil {
			lastErr = err
			continue
		}
		if resp.StatusCode >= 500 {
			_ = resp.Body.Close()
			lastErr = fmt.Errorf("status %d", resp.StatusCode)
			continue
		}
		return resp, nil
	}
	return nil, fmt.Errorf("discovery: probe failed after %d attempts: %w", attempts, lastErr)
}

// defaultsFor returns the NodeInfo a client should use when a node does
// not publish a discovery document, applying DefaultAPIPath to addr and
// DefaultAPIVersion as the protocol version.
func defaultsFor(addr string) NodeInfo {
	return NodeInfo{
		APIBaseURL: addr + DefaultAPIPath,
		APIVersion: DefaultAPIVersion,
	}
}

// validate checks that a parsed NodeInfo describes a node this client
// can talk to: a non-empty http(s) api_base_url and an api_version that
// matches SupportedAPIVersion. A mismatch is reported in domain terms
// ("upgrade the client") so the user sees an actionable message rather
// than a raw comparison failure.
func validate(info NodeInfo) error {
	if info.APIBaseURL == "" {
		return errors.New("api_base_url is required")
	}
	if !strings.HasPrefix(info.APIBaseURL, "http://") && !strings.HasPrefix(info.APIBaseURL, "https://") {
		return fmt.Errorf("api_base_url %q must be an http(s) URL", info.APIBaseURL)
	}
	if info.APIVersion == "" {
		return errors.New("api_version is required")
	}
	if info.APIVersion != SupportedAPIVersion {
		return fmt.Errorf("node speaks api_version %q but this client supports %q — upgrade the client", info.APIVersion, SupportedAPIVersion)
	}
	return nil
}
