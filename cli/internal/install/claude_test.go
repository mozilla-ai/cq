package install

import (
	"errors"
	"fmt"
	"testing"

	"github.com/stretchr/testify/require"
)

// recordedRun is one command that a stub runner received.
type recordedRun struct {
	// args is the full command line.
	args []string

	// dir is the working directory the command ran in.
	dir string
}

// recordRuns returns a runner that appends each command to ran and succeeds.
func recordRuns(ran *[]recordedRun) func(dir string, name string, args ...string) ([]byte, error) {
	return func(dir string, name string, args ...string) ([]byte, error) {
		*ran = append(*ran, recordedRun{args: append([]string{name}, args...), dir: dir})
		return nil, nil
	}
}

// stubLookPath returns a lookPath function that always succeeds.
func stubLookPath(string) (string, error) { return "/usr/bin/claude", nil }

func TestClaudeInstallRunsMarketplaceCommandsInScope(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name       string
		projectDir string
		scope      string
		detail     string
	}{
		{name: "global install uses user scope", projectDir: "", scope: "user", detail: "user scope"},
		{
			name:       "project install uses project scope",
			projectDir: "/work/app",
			scope:      "project",
			detail:     "project scope: /work/app",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			var ran []recordedRun
			h := claudeHost{lookPath: stubLookPath, run: recordRuns(&ran)}

			changes, err := h.Install(Context{DryRun: false, ProjectDir: tc.projectDir})
			require.NoError(t, err)
			require.Equal(t, []Change{
				{Action: ActionCreated, Path: "claude marketplace", Detail: tc.detail},
				{Action: ActionCreated, Path: "claude plugin", Detail: tc.detail},
			}, changes)

			require.Equal(t, []recordedRun{
				{
					dir: tc.projectDir,
					args: []string{
						"claude",
						"plugin",
						"marketplace",
						"add",
						claudeMarketplaceSource,
						"--scope",
						tc.scope,
					},
				},
				{
					dir:  tc.projectDir,
					args: []string{"claude", "plugin", "install", claudeMarketplaceID, "--scope", tc.scope},
				},
			}, ran)
		})
	}
}

func TestClaudeUninstallRemovesPluginThenMarketplaceInScope(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name       string
		projectDir string
		scope      string
		detail     string
	}{
		{name: "global uninstall uses user scope", projectDir: "", scope: "user", detail: "user scope"},
		{
			name:       "project uninstall uses project scope",
			projectDir: "/work/app",
			scope:      "project",
			detail:     "project scope: /work/app",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			var ran []recordedRun
			h := claudeHost{lookPath: stubLookPath, run: recordRuns(&ran)}

			changes, err := h.Uninstall(Context{DryRun: false, ProjectDir: tc.projectDir})
			require.NoError(t, err)
			require.Equal(t, []Change{
				{Action: ActionRemoved, Path: "claude plugin", Detail: tc.detail},
				{Action: ActionRemoved, Path: "claude marketplace", Detail: tc.detail},
			}, changes)

			require.Equal(t, []recordedRun{
				{
					dir:  tc.projectDir,
					args: []string{"claude", "plugin", "uninstall", claudeMarketplaceID, "--scope", tc.scope, "--json"},
				},
				{
					dir: tc.projectDir,
					args: []string{
						"claude", "plugin", "marketplace", "remove", claudeMarketplaceID, "--scope", tc.scope, "--json",
					},
				},
			}, ran)
		})
	}
}

func TestClaudeUninstallReportsAbsentStepsUnchanged(t *testing.T) {
	t.Parallel()

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
				run: func(_ string, _ string, args ...string) ([]byte, error) {
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
				{Action: ActionUnchanged, Path: "claude plugin", Detail: "user scope"},
				{Action: ActionUnchanged, Path: "claude marketplace", Detail: "user scope"},
			}, changes)
		})
	}
}

func TestClaudeUninstallPropagatesOtherFailures(t *testing.T) {
	t.Parallel()

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
				run: func(_ string, name string, _ ...string) ([]byte, error) {
					return []byte(tc.out), fmt.Errorf("running %s: exit status 1", name)
				},
			}

			_, err := h.Uninstall(Context{DryRun: false})
			require.ErrorContains(t, err, "exit status 1")
		})
	}
}

func TestClaudeInstallDryRunSkipsExecution(t *testing.T) {
	t.Parallel()

	var ran []recordedRun
	h := claudeHost{lookPath: stubLookPath, run: recordRuns(&ran)}

	changes, err := h.Install(Context{DryRun: true})
	require.NoError(t, err)
	require.Len(t, changes, 2)
	require.Equal(t, ActionCreated, changes[0].Action)
	require.Equal(t, ActionCreated, changes[1].Action)
	require.Empty(t, ran)
}

func TestClaudeDryRunFailsWhenCLIMissing(t *testing.T) {
	t.Parallel()

	h := claudeHost{
		lookPath: func(string) (string, error) {
			return "", errors.New("not found")
		},
	}

	_, err := h.Install(Context{DryRun: true})
	require.ErrorContains(t, err, "claude CLI not found on PATH")

	_, err = h.Uninstall(Context{DryRun: true})
	require.ErrorContains(t, err, "claude CLI not found on PATH")
}

func TestClaudeInstallPropagatesCommandFailure(t *testing.T) {
	t.Parallel()

	h := claudeHost{
		lookPath: stubLookPath,
		run: func(_ string, name string, _ ...string) ([]byte, error) {
			return nil, fmt.Errorf("running %s: exit status 1", name)
		},
	}

	_, err := h.Install(Context{DryRun: false})
	require.Error(t, err)
	require.Contains(t, err.Error(), "claude")
}

func TestClaudeInstallFailsWhenCLIMissing(t *testing.T) {
	t.Parallel()

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
	t.Parallel()

	h, ok := hosts[TargetClaude]
	require.True(t, ok)
	require.Equal(t, TargetClaude, h.Name())
	require.True(t, h.SupportsProject())
}
