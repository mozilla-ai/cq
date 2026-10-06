package install

import (
	"errors"
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
		run: func(name string, args ...string) ([]byte, error) {
			ran = append(ran, append([]string{name}, args...))
			return nil, nil
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

func TestClaudeUninstallRemovesPluginThenMarketplace(t *testing.T) {
	var ran [][]string
	h := claudeHost{
		lookPath: stubLookPath,
		run: func(name string, args ...string) ([]byte, error) {
			ran = append(ran, append([]string{name}, args...))
			return nil, nil
		},
	}

	changes, err := h.Uninstall(Context{DryRun: false})
	require.NoError(t, err)
	require.Equal(t, []Change{
		{Action: ActionRemoved, Path: "claude plugin"},
		{Action: ActionRemoved, Path: "claude marketplace"},
	}, changes)

	require.Len(t, ran, 2)
	require.Equal(t, []string{"claude", "plugin", "uninstall", claudeMarketplaceID, "--json"}, ran[0])
	require.Equal(t, []string{"claude", "plugin", "marketplace", "remove", claudeMarketplaceID, "--json"}, ran[1])
}

func TestClaudeUninstallReportsAbsentStepsUnchanged(t *testing.T) {
	tests := []struct {
		name       string
		pluginCode string
	}{
		{name: "plugin installed nowhere", pluginCode: "not_installed"},
		{name: "plugin installed only in another scope", pluginCode: "not_installed_at_scope"},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			h := claudeHost{
				lookPath: stubLookPath,
				run: func(_ string, args ...string) ([]byte, error) {
					code := tc.pluginCode
					if args[1] == "marketplace" {
						code = "not_configured"
					}
					out := fmt.Sprintf(`{"outcome":"failed","failureCode":"%s"}`, code)
					return []byte("progress\n" + out + "\n"), errors.New("exit status 1")
				},
			}

			changes, err := h.Uninstall(Context{DryRun: false})
			require.NoError(t, err)
			require.Equal(t, []Change{
				{Action: ActionUnchanged, Path: "claude plugin"},
				{Action: ActionUnchanged, Path: "claude marketplace"},
			}, changes)
		})
	}
}

func TestClaudeUninstallPropagatesOtherFailures(t *testing.T) {
	tests := []struct {
		name string
		out  string
	}{
		{name: "unrelated failure code", out: `{"outcome":"failed","failureCode":"permission_denied"}`},
		{name: "absent code for a different step", out: `{"outcome":"failed","failureCode":"not_configured"}`},
		{name: "no machine-readable result", out: "Error: unknown option '--json'"},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			h := claudeHost{
				lookPath: stubLookPath,
				run: func(name string, _ ...string) ([]byte, error) {
					return []byte(tc.out), fmt.Errorf("running %s: exit status 1", name)
				},
			}

			_, err := h.Uninstall(Context{DryRun: false})
			require.ErrorContains(t, err, "exit status 1")
		})
	}
}

func TestClaudeInstallDryRunSkipsExecution(t *testing.T) {
	var ran [][]string
	h := claudeHost{run: func(name string, args ...string) ([]byte, error) {
		ran = append(ran, append([]string{name}, args...))
		return nil, nil
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
		run: func(name string, args ...string) ([]byte, error) {
			return nil, fmt.Errorf("running %s: exit status 1", name)
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
