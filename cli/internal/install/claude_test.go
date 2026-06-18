package install

import (
	"fmt"
	"testing"

	"github.com/stretchr/testify/require"
)

// stubLookPath returns a lookPath function that always succeeds.
func stubLookPath(string) (string, error) { return "/usr/bin/claude", nil }

func TestClaudeInstallRunsMarketplaceCommands(t *testing.T) {
	var ran [][]string
	h := claudeHost{
		lookPath: stubLookPath,
		run: func(name string, args ...string) error {
			ran = append(ran, append([]string{name}, args...))
			return nil
		},
	}

	changes, err := h.Install(Context{DryRun: false})
	require.NoError(t, err)
	require.Len(t, changes, 1)
	require.Equal(t, ActionCreated, changes[0].Action)

	require.Len(t, ran, 2)
	require.Equal(t, []string{"claude", "plugin", "marketplace", "add", claudeMarketplaceSource}, ran[0])
	require.Equal(t, []string{"claude", "plugin", "install", claudeMarketplaceID}, ran[1])
}

func TestClaudeUninstallRunsMarketplaceRemove(t *testing.T) {
	var ran [][]string
	h := claudeHost{
		lookPath: stubLookPath,
		run: func(name string, args ...string) error {
			ran = append(ran, append([]string{name}, args...))
			return nil
		},
	}

	changes, err := h.Uninstall(Context{DryRun: false})
	require.NoError(t, err)
	require.Len(t, changes, 1)
	require.Equal(t, ActionRemoved, changes[0].Action)

	require.Len(t, ran, 1)
	require.Equal(t, []string{"claude", "plugin", "marketplace", "remove", claudeMarketplaceID}, ran[0])
}

func TestClaudeInstallDryRunSkipsExecution(t *testing.T) {
	var ran [][]string
	h := claudeHost{run: func(name string, args ...string) error {
		ran = append(ran, append([]string{name}, args...))
		return nil
	}}

	changes, err := h.Install(Context{DryRun: true})
	require.NoError(t, err)
	require.Len(t, changes, 1)
	require.Equal(t, ActionCreated, changes[0].Action)
	require.Empty(t, ran)
}

func TestClaudeInstallPropagatesCommandFailure(t *testing.T) {
	h := claudeHost{
		lookPath: stubLookPath,
		run: func(name string, args ...string) error {
			return fmt.Errorf("running %s: exit status 1", name)
		},
	}

	_, err := h.Install(Context{DryRun: false})
	require.Error(t, err)
	require.Contains(t, err.Error(), "claude")
}

func TestClaudeInstallFailsWhenCLIMissing(t *testing.T) {
	h := claudeHost{
		lookPath: func(string) (string, error) {
			return "", fmt.Errorf("not found")
		},
	}

	_, err := h.Install(Context{DryRun: false})
	require.Error(t, err)
	require.Contains(t, err.Error(), "claude CLI not found on PATH")
}

func TestClaudeRegisteredAndProject(t *testing.T) {
	h, ok := hosts[TargetClaude]
	require.True(t, ok)
	require.Equal(t, TargetClaude, h.Name())
	require.False(t, h.SupportsProject())
}
