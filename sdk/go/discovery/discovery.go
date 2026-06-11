package discovery

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Resolver maps a user-supplied cq node address to a NodeInfo by probing
// the node's discovery document at WellKnownPath.
// Successful resolutions are memoized in-process for the lifetime of the
// Resolver and persisted to disk so short-lived processes share results
// across invocations.
//
// Behavior:
//
//   - 404 from the discovery endpoint: returns documented defaults
//     (addr + DefaultAPIPath, DefaultAPIVersion). Cached.
//   - 200 with a valid document whose api_version matches
//     SupportedAPIVersion: parsed NodeInfo. Cached.
//   - 200 with text/html: error in domain terms (the address looks like
//     a SPA, not a cq node). Not cached.
//   - 200 with malformed JSON: error. Not cached.
//   - 200 with valid JSON but api_version mismatch: error naming both
//     versions. Not cached.
//   - 5xx, network error, timeout: retried once with a short backoff,
//     then error. Not cached.
//
// NOTE: a Resolver is safe for concurrent use; the in-process memo is
// guarded by a mutex and concurrent Resolve calls for the same address
// are coalesced into a single probe (single-flight).
type Resolver struct {
	fileCache *cache
	httpc     *http.Client
	logger    *slog.Logger

	mu       sync.Mutex
	memCache map[string]NodeInfo
	inflight map[string]*resolveCall
}

// resolveCall is the shared state of a single in-flight Resolve for one
// address.
// The elected goroutine creates it, runs the disk-cache check and
// network probe, and closes done; every concurrent caller for the same
// address reads info/err once done is closed and skips the probe.
// NOTE: info, err, and waiters must only be read or written with the
// owning Resolver's mu held until done is closed; after close, info and
// err are immutable and safe to read without the lock.
type resolveCall struct {
	done    chan struct{}
	info    NodeInfo
	err     error
	waiters int
}

// New constructs a Resolver from functional options.
// All configuration is optional; see defaultOptions for the values
// applied when an option is omitted, and WithCacheDir, WithHTTPClient,
// and WithLogger for the available overrides.
// NOTE: when the on-disk cache is enabled, its directory is created
// lazily on first successful write.
func New(opts ...Option) (*Resolver, error) {
	o := defaultOptions()
	for _, opt := range opts {
		if opt == nil {
			continue
		}
		if err := opt(&o); err != nil {
			return nil, fmt.Errorf("applying option: %w", err)
		}
	}
	var fc *cache
	if o.cacheDir != "" {
		fc = newCache(o.cacheDir, DefaultCacheTTL)
	}
	return &Resolver{
		fileCache: fc,
		httpc:     o.httpClient,
		logger:    o.logger,
		memCache:  map[string]NodeInfo{},
		inflight:  map[string]*resolveCall{},
	}, nil
}

// Resolve returns the NodeInfo for addr.
// Trailing slashes in addr are normalized away before lookup.
// Concurrent callers for the same address are coalesced: the first
// caller probes, every other caller waits for that probe's result and
// sees the same NodeInfo (or the same error).
// A failed probe is not memoized; the next caller retries the network.
func (r *Resolver) Resolve(ctx context.Context, addr string) (NodeInfo, error) {
	addr = strings.TrimRight(addr, "/")

	r.mu.Lock()
	if info, ok := r.memCache[addr]; ok {
		r.mu.Unlock()
		return info, nil
	}
	if call, ok := r.inflight[addr]; ok {
		call.waiters++
		r.mu.Unlock()
		select {
		case <-call.done:
			return call.info, call.err
		case <-ctx.Done():
			return NodeInfo{}, ctx.Err()
		}
	}
	call := &resolveCall{done: make(chan struct{})}
	r.inflight[addr] = call
	r.mu.Unlock()

	info, err := r.resolveUncached(ctx, addr)

	r.mu.Lock()
	call.info = info
	call.err = err
	if err == nil {
		r.memCache[addr] = info
	}
	delete(r.inflight, addr)
	// Close before releasing the lock so a new caller arriving on the
	// same addr cannot register a fresh probe while existing waiters
	// are still blocked on this call's done channel.
	close(call.done)
	r.mu.Unlock()

	return info, err
}

// resolveUncached runs the disk-cache check and network probe for addr.
// NOTE: callers must hold the single-flight election for addr;
// this helper does no in-process memoization and is not safe to call
// directly outside the Resolve flow.
func (r *Resolver) resolveUncached(ctx context.Context, addr string) (NodeInfo, error) {
	if r.fileCache != nil {
		if info, ok := r.fileCache.get(addr); ok {
			return info, nil
		}
	}

	info, err := r.probe(ctx, addr)
	if err != nil {
		return NodeInfo{}, err
	}

	if r.fileCache != nil {
		// Disk cache failure is non-fatal: the resolution itself is
		// valid for the lifetime of this process.
		// The warning surfaces persistent cache-dir permission issues
		// to anyone who has wired a logger; default callers stay silent.
		if err := r.fileCache.put(addr, info); err != nil {
			r.logger.Warn("discovery: cache write failed", "addr", addr, "err", err)
		}
	}
	return info, nil
}

// fetchWithRetry issues a GET to u and retries up to attempts times on
// transport errors and 5xx responses, with a short linear backoff
// between attempts.
// A 4xx response is returned without retry so that 404 (a documented
// success case) is distinguishable from genuine transient failure.
// NOTE: on success the returned response body must be closed.
func (r *Resolver) fetchWithRetry(ctx context.Context, u string, attempts int) (*http.Response, error) {
	var lastErr error
	for i := range attempts {
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

// probe fetches the discovery document for addr and turns it into a NodeInfo.
// A 404 yields the documented defaults; any other non-2xx status, an
// HTML body, malformed JSON, or a version mismatch becomes an error
// rather than a silent fallback.
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
		return NodeInfo{}, fmt.Errorf(
			"discovery: %s returned text/html — the address likely points at a SPA, not a cq node API",
			addr,
		)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, 64<<10))
	if err != nil {
		return NodeInfo{}, fmt.Errorf("discovery: read body: %w", err)
	}

	info, err := decodeNodeInfo(body)
	if err != nil {
		return NodeInfo{}, fmt.Errorf("discovery: %w", err)
	}

	if err := validate(info); err != nil {
		return NodeInfo{}, fmt.Errorf("discovery: %w", err)
	}
	return info, nil
}

// decodeNodeInfo parses a discovery document body into a NodeInfo.
// Unknown fields are rejected so a future schema addition cannot be
// silently parsed with this client's narrower assumptions; the JSON
// schema declares additionalProperties:false and this matches.
// Trailing content after the first JSON value is rejected too, so a
// body like `{"version":1,...} garbage` or two concatenated objects
// cannot smuggle past the strict-parsing contract via json.Decoder's
// default single-value semantics.
func decodeNodeInfo(body []byte) (NodeInfo, error) {
	dec := json.NewDecoder(bytes.NewReader(body))
	dec.DisallowUnknownFields()
	var info NodeInfo
	if err := dec.Decode(&info); err != nil {
		return NodeInfo{}, fmt.Errorf("parse body: %w", err)
	}
	if dec.More() {
		return NodeInfo{}, errors.New("parse body: unexpected trailing content")
	}
	return info, nil
}

// defaultsFor returns the NodeInfo applied when a node does not publish
// a discovery document: DefaultAPIPath appended to addr, with
// DefaultAPIVersion as the protocol version and SupportedDiscoveryVersion
// as the document schema version.
func defaultsFor(addr string) NodeInfo {
	return NodeInfo{
		Version:    SupportedDiscoveryVersion,
		APIBaseURL: addr + DefaultAPIPath,
		APIVersion: DefaultAPIVersion,
	}
}

// validate checks that a parsed NodeInfo describes a node speaking a
// protocol this client can talk to: a supported document schema
// version, a non-empty http(s) api_base_url, and an api_version equal
// to SupportedAPIVersion.
// Mismatches are reported in domain terms so users see actionable
// messages rather than raw comparison failures.
func validate(info NodeInfo) error {
	if info.Version != SupportedDiscoveryVersion {
		return fmt.Errorf(
			"discovery document declares version %d but this client supports %d — upgrade the client",
			info.Version,
			SupportedDiscoveryVersion,
		)
	}
	if info.APIBaseURL == "" {
		return errors.New("api_base_url is required")
	}
	parsed, err := url.Parse(info.APIBaseURL)
	if err != nil {
		return fmt.Errorf("api_base_url %q is not a valid URL: %w", info.APIBaseURL, err)
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return fmt.Errorf("api_base_url %q must use http or https scheme", info.APIBaseURL)
	}
	if parsed.Host == "" {
		return fmt.Errorf("api_base_url %q is missing a host", info.APIBaseURL)
	}
	// url.Parse already rejects non-numeric port segments, but it
	// accepts numeric ports outside the uint16 range (e.g.
	// "https://host:99999/").
	// Reject those here so the failure surfaces as a discovery-domain
	// message rather than an opaque transport error.
	if port := parsed.Port(); port != "" {
		if _, err := strconv.ParseUint(port, 10, 16); err != nil {
			return fmt.Errorf("api_base_url %q has an invalid port %q", info.APIBaseURL, port)
		}
	}
	if info.APIVersion == "" {
		return errors.New("api_version is required")
	}
	if info.APIVersion != SupportedAPIVersion {
		return fmt.Errorf(
			"node speaks api_version %q but this client supports %q — upgrade the client",
			info.APIVersion,
			SupportedAPIVersion,
		)
	}
	return nil
}
