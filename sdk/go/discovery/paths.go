package discovery

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// DefaultCacheDir returns the XDG-compliant location for the node
// discovery cache.
// When XDG_CACHE_HOME is set, it takes precedence and must be an
// absolute path per the XDG Base Directory Specification (which
// requires implementations to ignore relative values).
// Otherwise the path falls back to ~/.cache/cq/discovery.
// See: https://specifications.freedesktop.org/basedir-spec/latest/
// NOTE: the returned path is not created on disk; the Resolver creates
// it lazily on first successful write.
func DefaultCacheDir() (string, error) {
	if v, ok := os.LookupEnv("XDG_CACHE_HOME"); ok {
		v = strings.TrimSpace(v)
		if v != "" {
			if !filepath.IsAbs(v) {
				return "", fmt.Errorf("XDG_CACHE_HOME must be an absolute path, got %q", v)
			}
			return filepath.Join(v, "cq", "discovery"), nil
		}
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("locate user home: %w", err)
	}
	return filepath.Join(home, ".cache", "cq", "discovery"), nil
}
