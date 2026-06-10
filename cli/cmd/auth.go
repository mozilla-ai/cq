package cmd

import (
	"errors"
	"fmt"
	"sort"
	"strings"

	"github.com/spf13/cobra"

	"github.com/mozilla-ai/cq/cli/internal/auth"
	"github.com/mozilla-ai/cq/cli/internal/credstore"
)

// authLoginLongDoc is the help text shown for "cq auth login".
var authLoginLongDoc = fmt.Sprintf(`Sign in via a browser-based OIDC flow.

cq starts a short-lived listener on 127.0.0.1, asks the platform for an
authorization URL, opens the user's browser to it, and waits for the
provider's redirect back to the loopback. The captured code is exchanged
for a session JWT which is persisted to the local credential store.

Run "cq auth providers" to see the providers configured on the platform.

Notes:
  * On macOS the credential store uses Keychain. With the cq binary
    distributed unsigned, that store is no more resistant to same-user
    processes than a chmod-600 file in your home directory; future work
    will switch to ACL-protected storage once code signing infra exists.

  * Long-lived API keys are not part of this flow. Set %s for
    data-plane commands like cq propose / cq query.`,
	envVarAPIKey,
)

// authLogoutLongDoc is the help text shown for "cq auth logout".
var authLogoutLongDoc = `Clear locally-stored sign-in credentials.

By default, this command is local-only: it removes the session JWT and
cached identity from the credential store.

When configured, logout can also request server-side session revocation
before local credentials are cleared.

If server revocation fails for reasons other than an already-invalid
session, local credentials are left intact so you can retry.`

// authLongDoc is the help text shown for the "cq auth" parent command.
var authLongDoc = fmt.Sprintf(`Manage interactive sign-in for the cq platform.

cq auth covers control-plane operations: signing in via your identity
provider, inspecting the current session, and clearing the locally-stored
credentials.

Long-lived API keys for data-plane commands are configured separately
via the %s environment variable; cq auth never stores or prints them.`,
	envVarAPIKey,
)

// authProvidersLongDoc is the help text shown for "cq auth providers".
var authProvidersLongDoc = `List the OIDC providers enabled on the configured platform.

Output is one machine-readable provider name per line, ready to be passed
straight to "cq auth login" or piped into another command.`

// authStatusLongDoc is the help text shown for "cq auth status".
var authStatusLongDoc = `Show the current sign-in state.

Reports the configured server, the cached identity from the last
sign-in, and the session expiry when known. Exits non-zero when no
credentials are stored, so shell scripts can gate on sign-in:

    cq auth status >/dev/null || cq auth login github

This command is local-only and does not contact the platform; the
session's actual validity is observed when you run a control-plane
command.`

// authOptions holds the resolved configuration for the auth command
// tree. Callers configure it indirectly by passing AuthOption values
// to NewAuthCmd; the struct itself is unexported so the public surface
// is the With* option set rather than struct mutation.
type authOptions struct {
	// newStore opens the credstore.Store used by the subcommands.
	newStore func() (credstore.Store, error)

	// newClient builds the platform HTTP client used by the
	// subcommands.
	newClient func(addr string) auth.Client
}

// AuthOption configures NewAuthCmd. Options are applied left-to-right
// over the defaults wired to the production credstore and auth client.
type AuthOption func(*authOptions)

// NewAuthCmd returns the "cq auth" parent command and its login,
// logout, providers, and status subcommands. Variadic AuthOptions
// override the defaults wired to credstore.New and auth.NewClient.
func NewAuthCmd(opts ...AuthOption) *cobra.Command {
	cfg := authOptions{
		newStore: func() (credstore.Store, error) {
			dir, err := configDir()
			if err != nil {
				return nil, err
			}

			return credstore.New(dir)
		},
		newClient: auth.NewClient,
	}
	for _, opt := range opts {
		if opt != nil {
			opt(&cfg)
		}
	}

	cmd := &cobra.Command{
		Use:   "auth",
		Short: "Manage interactive sign-in for the cq platform.",
		Long:  authLongDoc,
	}

	cmd.AddCommand(newAuthKeyCmd(cfg))
	cmd.AddCommand(newAuthLoginCmd(cfg))
	cmd.AddCommand(newAuthLogoutCmd(cfg))
	cmd.AddCommand(newAuthProvidersCmd(cfg))
	cmd.AddCommand(newAuthStatusCmd(cfg))

	return cmd
}

// WithAuthClient overrides how the auth subcommands obtain their
// platform HTTP client. Production callers do not need this; it is
// supplied so cobra-level tests can substitute a stub.
func WithAuthClient(fn func(addr string) auth.Client) AuthOption {
	return func(o *authOptions) { o.newClient = fn }
}

// WithCredStore overrides how the auth subcommands obtain their
// credstore.Store. Production callers do not need this; it is supplied
// so cobra-level tests can substitute an in-memory implementation.
func WithCredStore(fn func() (credstore.Store, error)) AuthOption {
	return func(o *authOptions) { o.newStore = fn }
}

// newAuthLoginCmd returns the "cq auth login" subcommand.
func newAuthLoginCmd(cfg authOptions) *cobra.Command {
	return &cobra.Command{
		Use:   "login <provider>",
		Short: "Sign in via a browser-based OIDC flow.",
		Long:  authLoginLongDoc,
		Args: func(_ *cobra.Command, args []string) error {
			if len(args) != 1 || strings.TrimSpace(args[0]) == "" {
				return errors.New(`provider required. Run "cq auth providers" to see options`)
			}

			return nil
		},
		RunE: func(cmd *cobra.Command, args []string) error {
			addr, err := requireAuthAddr()
			if err != nil {
				return err
			}

			store, err := cfg.newStore()
			if err != nil {
				return fmt.Errorf("opening credential store: %w", err)
			}

			return auth.Login(cmd.Context(), auth.LoginConfig{
				Provider: strings.ToLower(strings.TrimSpace(args[0])),
				Client:   cfg.newClient(addr),
				Store:    store,
				In:       cmd.InOrStdin(),
				Out:      cmd.OutOrStdout(),
			})
		},
	}
}

// newAuthLogoutCmd returns the "cq auth logout" subcommand.
func newAuthLogoutCmd(cfg authOptions) *cobra.Command {
	var (
		revoke     bool
		allDevices bool
	)

	cmd := &cobra.Command{
		Use:   "logout [--revoke] [--all-devices]",
		Short: "Clear locally-stored sign-in credentials.",
		Long:  authLogoutLongDoc,
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if allDevices && !revoke {
				return errors.New("--all-devices requires --revoke")
			}

			var client auth.Client
			if revoke {
				addr, err := requireAuthAddr()
				if err != nil {
					return err
				}

				client = cfg.newClient(addr)
			}

			store, err := cfg.newStore()
			if err != nil {
				return fmt.Errorf("opening credential store: %w", err)
			}

			return auth.Logout(cmd.Context(), auth.LogoutConfig{
				Store:      store,
				Client:     client,
				Revoke:     revoke,
				AllDevices: allDevices,
				Out:        cmd.OutOrStdout(),
			})
		},
	}

	cmd.Flags().BoolVar(
		&revoke,
		"revoke",
		false,
		"Request server-side session revocation before local cleanup.",
	)
	cmd.Flags().BoolVar(
		&allDevices,
		"all-devices",
		false,
		"Request server-side revocation across all devices/sessions (requires --revoke).",
	)

	return cmd
}

// newAuthProvidersCmd returns the "cq auth providers" subcommand: a
// read-only query of the platform's enabled OIDC providers, intended
// to make "cq auth login <provider>" discoverable without forcing the
// user to trigger an error first.
func newAuthProvidersCmd(cfg authOptions) *cobra.Command {
	return &cobra.Command{
		Use:   "providers",
		Short: "List the OIDC providers enabled on the configured platform.",
		Long:  authProvidersLongDoc,
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			addr, err := requireAuthAddr()
			if err != nil {
				return err
			}

			providers, err := cfg.newClient(addr).OAuthProviders(cmd.Context())
			if err != nil {
				return fmt.Errorf("fetching providers: %w", err)
			}

			enabled := make([]auth.Provider, 0, len(providers))
			for _, p := range providers {
				if p.Enabled {
					enabled = append(enabled, p)
				}
			}

			sort.Slice(enabled, func(i, j int) bool { return enabled[i].Name < enabled[j].Name })

			out := cmd.OutOrStdout()
			for _, p := range enabled {
				_, _ = fmt.Fprintln(out, p.Name)
			}

			return nil
		},
	}
}

// newAuthStatusCmd returns the "cq auth status" subcommand.
func newAuthStatusCmd(cfg authOptions) *cobra.Command {
	return &cobra.Command{
		Use:   "status",
		Short: "Show the current sign-in state.",
		Long:  authStatusLongDoc,
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			store, err := cfg.newStore()
			if err != nil {
				return fmt.Errorf("opening credential store: %w", err)
			}

			err = auth.Status(cmd.Context(), auth.StatusConfig{
				Store:  store,
				Server: flagAddr,
				Out:    cmd.OutOrStdout(),
			})
			if errors.Is(err, credstore.ErrNotFound) {
				// auth.Status already wrote a user-friendly message;
				// suppress cobra's default error rendering and let the
				// non-zero exit do the talking for shell scripts.
				cmd.SilenceErrors = true
				cmd.SilenceUsage = true
			}

			return err
		},
	}
}

// requireAuthAddr returns the effective platform address from --addr
// or the environment, erroring if neither is configured.
// Subcommands: login, providers, and logout --revoke need a real URL.
func requireAuthAddr() (string, error) {
	if flagAddr == "" {
		return "", fmt.Errorf("no platform address configured. Set %s or pass --addr", envVarAddr)
	}

	return flagAddr, nil
}
