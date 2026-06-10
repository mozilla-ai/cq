package discovery

import (
	"fmt"
	"log/slog"
	"net/http"
	"path/filepath"
	"strings"
	"time"
)

// Option configures a Resolver constructed via New.
type Option func(*options) error

// options holds resolved configuration for a Resolver instance.
// Defaults live in defaultOptions; WithX functions override them.
type options struct {
	// cacheDir is the on-disk cache directory for discovery results.
	// An empty value disables the on-disk cache; resolution still
	// memoizes in-process for the lifetime of the Resolver.
	cacheDir string

	// httpClient is the client used to issue the discovery probe.
	httpClient *http.Client

	// logger receives structured resolver diagnostics.
	logger *slog.Logger
}

// defaultOptions returns the configuration applied to a Resolver when
// no overriding options are passed.
// This is the single source of truth for default values:
// The on-disk cache is disabled (cacheDir empty so no file IO is attempted).
// The HTTP client uses a short timeout suitable for a well-known probe.
// The logger discards every record so the package is silent under MCP-over-stdio usage.
func defaultOptions() options {
	return options{
		cacheDir:   "",
		httpClient: &http.Client{Timeout: 5 * time.Second},
		logger:     slog.New(slog.DiscardHandler),
	}
}

// WithCacheDir enables the on-disk cache rooted at dir.
// dir must be a non-empty absolute path; relative paths are rejected
// to avoid the footgun of caching relative to the process's current
// working directory.
// When this option is omitted, the on-disk cache is disabled and the
// Resolver memoizes results in-process only — suitable for restricted
// or container environments without HOME/XDG_CACHE_HOME.
func WithCacheDir(dir string) Option {
	return func(o *options) error {
		dir = strings.TrimSpace(dir)
		if dir == "" {
			return fmt.Errorf("cache directory cannot be empty")
		}
		if !filepath.IsAbs(dir) {
			return fmt.Errorf("cache directory must be an absolute path, got %q", dir)
		}
		o.cacheDir = dir
		return nil
	}
}

// WithHTTPClient overrides the HTTP client used for the discovery probe.
// See defaultOptions for the value used when this option is omitted.
func WithHTTPClient(c *http.Client) Option {
	return func(o *options) error {
		if c == nil {
			return fmt.Errorf("http client cannot be nil")
		}
		o.httpClient = c
		return nil
	}
}

// WithLogger installs a structured logger for resolver diagnostics.
// See defaultOptions for the value used when this option is omitted;
// note that the default is silent and that this matters for the MCP
// transport where stdout carries JSONRPC.
func WithLogger(l *slog.Logger) Option {
	return func(o *options) error {
		if l == nil {
			return fmt.Errorf("logger cannot be nil")
		}
		o.logger = l
		return nil
	}
}
