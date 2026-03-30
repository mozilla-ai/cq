package cq

import (
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

// -- resolveConfig tests --

func TestDefaultConfig(t *testing.T) {
	t.Setenv("CQ_ADDR", "")
	t.Setenv("CQ_TEAM_ADDR", "")
	t.Setenv("CQ_API_KEY", "")
	t.Setenv("CQ_LOCAL_DB_PATH", "")

	cfg, err := resolveConfig()
	require.NoError(t, err)
	require.Empty(t, cfg.addr)
	require.Empty(t, cfg.apiKey)
	require.NotEmpty(t, cfg.localDBPath)
	require.Equal(t, DefaultTimeout(), cfg.timeout)
}

func TestConfigReadsEnvVars(t *testing.T) {
	t.Setenv("CQ_ADDR", "http://localhost:8742")
	t.Setenv("CQ_TEAM_ADDR", "")
	t.Setenv("CQ_API_KEY", "test-key")
	t.Setenv("CQ_LOCAL_DB_PATH", "/tmp/test.db")

	cfg, err := resolveConfig()
	require.NoError(t, err)
	require.Equal(t, "http://localhost:8742", cfg.addr)
	require.Equal(t, "test-key", cfg.apiKey)
	require.Equal(t, "/tmp/test.db", cfg.localDBPath)
}

func TestConfigReadsCQTeamAddr(t *testing.T) {
	t.Setenv("CQ_ADDR", "http://old-addr:8742")
	t.Setenv("CQ_TEAM_ADDR", "http://team-addr:9999")
	t.Setenv("CQ_API_KEY", "")
	t.Setenv("CQ_LOCAL_DB_PATH", "/tmp/test.db")

	cfg, err := resolveConfig()
	require.NoError(t, err)
	require.Equal(t, "http://team-addr:9999", cfg.addr)
}

func TestConfigCQTeamAddrAloneWorks(t *testing.T) {
	t.Setenv("CQ_ADDR", "")
	t.Setenv("CQ_TEAM_ADDR", "http://team-only:9999")
	t.Setenv("CQ_API_KEY", "")
	t.Setenv("CQ_LOCAL_DB_PATH", "/tmp/test.db")

	cfg, err := resolveConfig()
	require.NoError(t, err)
	require.Equal(t, "http://team-only:9999", cfg.addr)
}

func TestConfigExpandsTildeInEnvVar(t *testing.T) {
	t.Setenv("CQ_LOCAL_DB_PATH", "~/cq/test.db")
	t.Setenv("CQ_ADDR", "")
	t.Setenv("CQ_TEAM_ADDR", "")
	t.Setenv("CQ_API_KEY", "")

	cfg, err := resolveConfig()
	require.NoError(t, err)

	home, _ := os.UserHomeDir()
	require.Equal(t, filepath.Join(home, "cq/test.db"), cfg.localDBPath)
}

func TestOptionOverridesEnv(t *testing.T) {
	t.Setenv("CQ_ADDR", "http://from-env:8742")
	t.Setenv("CQ_TEAM_ADDR", "")

	cfg, err := resolveConfig(
		WithAddr("http://from-option:9999"),
		WithAPIKey("option-key"),
		WithLocalDBPath("/tmp/option.db"),
		WithTimeout(10*time.Second),
	)
	require.NoError(t, err)
	require.Equal(t, "http://from-option:9999", cfg.addr)
	require.Equal(t, "option-key", cfg.apiKey)
	require.Equal(t, "/tmp/option.db", cfg.localDBPath)
	require.Equal(t, 10*time.Second, cfg.timeout)
}

func TestWithTimeoutRejectsNonPositive(t *testing.T) {
	_, err := resolveConfig(WithTimeout(0))
	require.Error(t, err)
	require.Contains(t, err.Error(), "timeout must be positive")
}

func TestNilOptionIsSkipped(t *testing.T) {
	t.Setenv("CQ_ADDR", "")
	t.Setenv("CQ_TEAM_ADDR", "")
	t.Setenv("CQ_API_KEY", "")
	t.Setenv("CQ_LOCAL_DB_PATH", "")

	cfg, err := resolveConfig(nil, WithAddr("http://test:8742"), nil)
	require.NoError(t, err)
	require.Equal(t, "http://test:8742", cfg.addr)
}

// -- expandHome tests --

func TestExpandHome(t *testing.T) {
	t.Parallel()

	home, err := os.UserHomeDir()
	require.NoError(t, err)

	tc := []struct {
		name     string
		input    string
		expected string
	}{
		{name: "tilde with slash", input: "~/foo/bar", expected: filepath.Join(home, "foo/bar")},
		{name: "tilde only", input: "~", expected: home},
		{name: "tilde db path", input: "~/cq/test.db", expected: filepath.Join(home, "cq/test.db")},
		{name: "absolute path", input: "/tmp/test.db", expected: "/tmp/test.db"},
		{name: "relative path", input: "relative/path", expected: "relative/path"},
		{name: "empty string", input: "", expected: ""},
	}

	for _, tc := range tc {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			result, err := expandHome(tc.input)
			require.NoError(t, err)
			require.Equal(t, tc.expected, result)
		})
	}
}

// -- defaultLocalDBPath tests --

func TestDefaultLocalDBPathUsesXDG(t *testing.T) {
	t.Setenv("XDG_DATA_HOME", "/custom/xdg")
	t.Setenv("HOME", t.TempDir())

	path, err := defaultLocalDBPath()
	require.NoError(t, err)
	require.Equal(t, "/custom/xdg/cq/local.db", path)
}

func TestDefaultLocalDBPathIgnoresRelativeXDG(t *testing.T) {
	t.Setenv("XDG_DATA_HOME", "relative/path")

	path, err := defaultLocalDBPath()
	require.NoError(t, err)

	// Should fall back to home-based path, not use relative XDG.
	home, _ := os.UserHomeDir()
	require.Equal(t, filepath.Join(home, ".local", "share", "cq", "local.db"), path)
}

func TestDefaultLocalDBPathFallsBackToHome(t *testing.T) {
	t.Setenv("XDG_DATA_HOME", "")

	path, err := defaultLocalDBPath()
	require.NoError(t, err)

	home, _ := os.UserHomeDir()
	require.Equal(t, filepath.Join(home, ".local", "share", "cq", "local.db"), path)
}

func TestDefaultLocalDBPathNoLegacyNoXDG(t *testing.T) {
	t.Setenv("XDG_DATA_HOME", "")
	tmpHome := t.TempDir()
	t.Setenv("HOME", tmpHome)

	path, err := defaultLocalDBPath()
	require.NoError(t, err)

	expected := filepath.Join(tmpHome, ".local", "share", "cq", "local.db")
	require.Equal(t, expected, path)
}

func TestResolvedLocalDBPath(t *testing.T) {
	t.Setenv("CQ_ADDR", "")
	t.Setenv("CQ_TEAM_ADDR", "")
	t.Setenv("CQ_API_KEY", "")
	t.Setenv("CQ_LOCAL_DB_PATH", "/explicit/path.db")

	path, err := ResolvedLocalDBPath()
	require.NoError(t, err)
	require.Equal(t, "/explicit/path.db", path)
}

func TestResolvedLocalDBPathWithOption(t *testing.T) {
	t.Setenv("CQ_LOCAL_DB_PATH", "")
	t.Setenv("CQ_ADDR", "")
	t.Setenv("CQ_TEAM_ADDR", "")
	t.Setenv("CQ_API_KEY", "")

	path, err := ResolvedLocalDBPath(WithLocalDBPath("/from/option.db"))
	require.NoError(t, err)
	require.Equal(t, "/from/option.db", path)
}
