package cmd

import (
	"context"
	"path/filepath"
	"testing"

	"github.com/spf13/pflag"
	"github.com/stretchr/testify/require"
)

func TestInitFlagsRegistersAllFlags(t *testing.T) {
	fs := pflag.NewFlagSet("test", pflag.ContinueOnError)
	InitFlags(fs)

	for _, name := range []string{"addr", "api-key", "db-path"} {
		require.NotNil(t, fs.Lookup(name), "expected flag %s to be registered", name)
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
