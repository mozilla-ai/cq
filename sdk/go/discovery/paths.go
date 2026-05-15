package discovery

import (
	"fmt"
	"os"
	"path/filepath"
)

// DefaultCacheDir returns the XDG-compliant location for the node
// discovery cache.
// XDG_CACHE_HOME takes precedence; otherwise ~/.cache/cq/discovery.
// NOTE: the returned path is not created on disk; the Resolver creates
// it lazily on first successful write.
func DefaultCacheDir() (string, error) {
	if v := os.Getenv("XDG_CACHE_HOME"); v != "" {
		return filepath.Join(v, "cq", "discovery"), nil
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("locate user home: %w", err)
	}
	return filepath.Join(home, ".cache", "cq", "discovery"), nil
}
