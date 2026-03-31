package cq

import (
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// defaultClientTimeout is the HTTP request timeout used when no override is provided.
const defaultClientTimeout = 5 * time.Second

// clientConfig holds resolved configuration for a Client instance.
type clientConfig struct {
	addr        string
	apiKey      string
	localDBPath string
	timeout     time.Duration
}

// ClientOption configures a Client.
type ClientOption func(*clientConfig) error

// DefaultTimeout is the default HTTP request timeout.
func DefaultTimeout() time.Duration {
	return defaultClientTimeout
}

// ResolvedLocalDBPath returns the local database path after applying
// environment variable resolution.
// Use this when you need the path without opening a full Client.
func ResolvedLocalDBPath(opts ...ClientOption) (string, error) {
	cfg, err := resolveConfig(opts...)
	if err != nil {
		return "", err
	}

	return cfg.localDBPath, nil
}

// WithAddr overrides the CQ_TEAM_ADDR / CQ_ADDR environment variable.
func WithAddr(addr string) ClientOption {
	return func(c *clientConfig) error {
		c.addr = addr

		return nil
	}
}

// WithAPIKey overrides the CQ_API_KEY environment variable.
func WithAPIKey(key string) ClientOption {
	return func(c *clientConfig) error {
		c.apiKey = key // pragma: allowlist secret

		return nil
	}
}

// WithLocalDBPath overrides the CQ_LOCAL_DB_PATH environment variable.
// Expands a leading ~ to the user's home directory.
func WithLocalDBPath(path string) ClientOption {
	return func(c *clientConfig) error {
		expanded, err := expandHome(path)
		if err != nil {
			return err
		}

		c.localDBPath = expanded

		return nil
	}
}

// WithTimeout overrides the default HTTP request timeout.
func WithTimeout(d time.Duration) ClientOption {
	return func(c *clientConfig) error {
		if d <= 0 {
			return fmt.Errorf("timeout must be positive, got %v", d)
		}
		c.timeout = d

		return nil
	}
}

// defaultConfig returns a clientConfig populated with compile-time defaults.
func defaultConfig() clientConfig {
	return clientConfig{
		timeout: DefaultTimeout(),
	}
}

// defaultLocalDBPath returns the platform-appropriate default database path, respecting XDG_DATA_HOME.
func defaultLocalDBPath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("cannot determine home directory for default DB path: %w", err)
	}

	var dataHome string
	if xdg := os.Getenv("XDG_DATA_HOME"); xdg != "" && filepath.IsAbs(xdg) {
		dataHome = xdg
	} else {
		dataHome = filepath.Join(home, ".local", "share")
	}

	return filepath.Join(dataHome, "cq", "local.db"), nil
}

// expandHome replaces a leading ~ in path with the user's home directory.
func expandHome(path string) (string, error) {
	if len(path) == 0 || path[0] != '~' {
		return path, nil
	}

	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("expanding home directory: %w", err)
	}

	return filepath.Join(home, path[1:]), nil
}

// resolveConfig builds a clientConfig from defaults, env vars, and options.
// Precedence: defaults < env vars < options.
// CQ_TEAM_ADDR takes precedence over CQ_ADDR for the remote address.
func resolveConfig(opts ...ClientOption) (*clientConfig, error) {
	cfg := defaultConfig()

	if v := os.Getenv("CQ_ADDR"); v != "" {
		cfg.addr = v
	}

	// CQ_TEAM_ADDR takes precedence over CQ_ADDR.
	if v := os.Getenv("CQ_TEAM_ADDR"); v != "" {
		cfg.addr = v
	}

	if v := os.Getenv("CQ_API_KEY"); v != "" {
		cfg.apiKey = v
	}

	if v := os.Getenv("CQ_LOCAL_DB_PATH"); v != "" {
		expanded, err := expandHome(v)
		if err != nil {
			return nil, err
		}

		cfg.localDBPath = expanded
	}

	for _, opt := range opts {
		if opt == nil {
			continue
		}
		if err := opt(&cfg); err != nil {
			return nil, fmt.Errorf("applying option: %w", err)
		}
	}

	if cfg.localDBPath == "" {
		path, err := defaultLocalDBPath()
		if err != nil {
			return nil, err
		}

		cfg.localDBPath = path
	}

	return &cfg, nil
}
