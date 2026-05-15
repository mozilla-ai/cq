package cq

import (
	"fmt"
	"os"
	"path/filepath"
)

// defaultDiscoveryCacheDir returns the XDG-compliant location for the
// node discovery cache.
// XDG_CACHE_HOME takes precedence; otherwise ~/.cache/cq/discovery.
func defaultDiscoveryCacheDir() (string, error) {
	if v := os.Getenv("XDG_CACHE_HOME"); v != "" {
		return filepath.Join(v, "cq", "discovery"), nil
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("locate user home: %w", err)
	}
	return filepath.Join(home, ".cache", "cq", "discovery"), nil
}
