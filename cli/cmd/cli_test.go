package cmd

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"github.com/spf13/pflag"
	"github.com/stretchr/testify/require"
)

func TestInitFlagsRegistersAllFlags(t *testing.T) {
	fs := pflag.NewFlagSet("test", pflag.ContinueOnError)
	InitFlags(fs)

	for _, name := range []string{"addr", "api-key", "db-path", "timeout"} {
		require.NotNil(t, fs.Lookup(name), "expected flag %s to be registered", name)
	}
}

func TestInitFlagsTimeoutUsesZeroSentinelDefault(t *testing.T) {
	fs := pflag.NewFlagSet("test", pflag.ContinueOnError)
	InitFlags(fs)

	f := fs.Lookup("timeout")
	require.NotNil(t, f)

	// The flag carries a 0 sentinel so flag > env > default resolution stays in
	// cliTimeout. Because 0 is the zero value for a duration, pflag suppresses a
	// misleading "(default 0s)"; the real default is documented in the usage.
	require.Equal(t, "0s", f.DefValue)
	require.Contains(t, f.Usage, envVarTimeout)
	require.Contains(t, f.Usage, "default "+defaultCLITimeout.String())
	require.NotContains(t, fs.FlagUsages(), "(default 0s)")

	// The env var is parsed as integer seconds (unlike the duration flag), so
	// the help must document the unit to avoid a silent fallback on e.g.
	// CQ_TIMEOUT=30s.
	require.Contains(t, f.Usage, "seconds")
}

func TestInitFlagsParsesTimeoutDuration(t *testing.T) {
	setFlag(t, &flagTimeout, 0)

	fs := pflag.NewFlagSet("test", pflag.ContinueOnError)
	InitFlags(fs)

	require.NoError(t, fs.Parse([]string{"--timeout=1m30s"}))
	require.Equal(t, 90*time.Second, flagTimeout)
}

func TestInitFlagsRejectsInvalidTimeout(t *testing.T) {
	setFlag(t, &flagTimeout, 0)

	fs := pflag.NewFlagSet("test", pflag.ContinueOnError)
	InitFlags(fs)

	require.Error(t, fs.Parse([]string{"--timeout=not-a-duration"}))
}

func TestCLITimeout(t *testing.T) {
	tests := []struct {
		name string
		flag time.Duration
		env  string
		want time.Duration
	}{
		{name: "flag overrides env and default", flag: 3 * time.Second, env: "8", want: 3 * time.Second},
		{name: "flag honors sub-second durations", flag: 500 * time.Millisecond, env: "", want: 500 * time.Millisecond},
		{name: "env used when flag unset", flag: 0, env: "8", want: 8 * time.Second},
		{name: "default when flag and env unset", flag: 0, env: "", want: defaultCLITimeout},
		{name: "default when env is non-numeric", flag: 0, env: "abc", want: defaultCLITimeout},
		{name: "default when env is non-positive", flag: 0, env: "0", want: defaultCLITimeout},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Setenv(envVarTimeout, tc.env)
			setFlag(t, &flagTimeout, tc.flag)

			require.Equal(t, tc.want, cliTimeout())
		})
	}
}

func TestInitFlagsDefaultsFromEnv(t *testing.T) {
	t.Setenv(envVarAddr, "http://test:8742")
	t.Setenv(envVarAPIKey, "test-key")
	t.Setenv(envVarDBPath, "/tmp/test.db")

	fs := pflag.NewFlagSet("test", pflag.ContinueOnError)
	InitFlags(fs)

	require.Equal(t, "http://test:8742", fs.Lookup("addr").DefValue)
	require.Empty(t, fs.Lookup("api-key").DefValue, "api-key default should never expose the secret")
	require.Equal(t, "/tmp/test.db", fs.Lookup("db-path").DefValue)
}

func TestInitFlagsEmptyWhenEnvUnset(t *testing.T) {
	t.Setenv(envVarAddr, "")
	t.Setenv(envVarAPIKey, "")
	t.Setenv(envVarDBPath, "")

	fs := pflag.NewFlagSet("test", pflag.ContinueOnError)
	InitFlags(fs)

	require.Empty(t, fs.Lookup("addr").DefValue)
	require.Empty(t, fs.Lookup("api-key").DefValue)
	require.Empty(t, fs.Lookup("db-path").DefValue)
}

func TestNewCLIClientRespectsDBPath(t *testing.T) {
	testSetup(t)

	customPath := t.TempDir() + "/custom.db"
	setFlag(t, &flagDBPath, customPath)

	c, err := newCLIClient()
	require.NoError(t, err)
	defer func() { _ = c.Close() }()

	// Verify client works with the custom path.
	stats, err := c.Status(context.Background())
	require.NoError(t, err)
	require.Equal(t, 0, stats.TotalCount)
}

func TestNewCLIClientRespectsAPIKey(t *testing.T) {
	testSetup(t)
	setFlag(t, &flagAPIKey, "test-key-value")

	// Should not error; the key is passed through to the SDK.
	c, err := newCLIClient()
	require.NoError(t, err)
	defer func() { _ = c.Close() }()
}

func TestConfigDir_CQOverrideTakesPriority(t *testing.T) {
	t.Setenv(envVarConfigDir, "/explicit/override")
	t.Setenv(envVarXDGConfigHome, "/xdg/path")
	t.Setenv("HOME", "/home/user")

	got, err := configDir()
	require.NoError(t, err)
	require.Equal(t, "/explicit/override", got)
}

func TestConfigDir_FallsBackToXDGConfigHome(t *testing.T) {
	t.Setenv(envVarConfigDir, "")
	t.Setenv(envVarXDGConfigHome, "/xdg/path")
	t.Setenv("HOME", "/home/user")

	got, err := configDir()
	require.NoError(t, err)
	require.Equal(t, filepath.Join("/xdg/path", "cq"), got)
}

func TestConfigDir_IgnoresRelativeXDGConfigHome(t *testing.T) {
	t.Setenv(envVarConfigDir, "")
	t.Setenv(envVarXDGConfigHome, "relative/path")
	t.Setenv("HOME", "/home/user")

	got, err := configDir()
	require.NoError(t, err)
	require.Equal(t, filepath.Join("/home/user", ".config", "cq"), got)
}

func TestConfigDir_FallsBackToHomeConfig(t *testing.T) {
	t.Setenv(envVarConfigDir, "")
	t.Setenv(envVarXDGConfigHome, "")
	t.Setenv("HOME", "/home/user")

	got, err := configDir()
	require.NoError(t, err)
	require.Equal(t, filepath.Join("/home/user", ".config", "cq"), got)
}
