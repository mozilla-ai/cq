package cmd

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/mozilla-ai/cq/sdk/go/ttl"

	"github.com/mozilla-ai/cq/cli/internal/auth"
	"github.com/mozilla-ai/cq/cli/internal/credstore"
)

// authKeyCreateLongDoc is the help text shown for cq auth key create.
var authKeyCreateLongDoc = `Create a new API key.

The API key is shown exactly once, on stdout, so it can be captured by
a shell script with command substitution:

    KEY=$(cq auth key create --name claude-cursor --ttl 90d)

Human-readable status (the key's ID, prefix, and expiry) is written to
stderr so it does not contaminate the captured value. The API key is
not recoverable after this command returns; if you lose it, revoke the
key and create a new one.`

// authKeyListLongDoc is the help text shown for cq auth key list.
var authKeyListLongDoc = `List your API keys.

The platform never returns API keys themselves; only metadata is
shown. Revoked and expired keys are included so you can audit your own
revocation history.

Use --json for machine-readable output suitable for piping into jq or
similar tooling.`

// authKeyLongDoc is the help text shown for the cq auth key parent
// command.
var authKeyLongDoc = `Manage long-lived API keys for the authenticated user.

API keys authenticate data-plane commands (cq propose, cq confirm,
cq flag, ...). Each key is independent: revoking one does not affect
any other key. Keys are scoped to the human account; the key name and
labels are metadata for the operator, not a separate identity.

All subcommands here use the session JWT stored by cq auth login, not
an API key. If your session has expired, run cq auth login again.`

// authKeyRevokeLongDoc is the help text shown for cq auth key revoke.
var authKeyRevokeLongDoc = `Revoke an API key by its ID.

Revocation is idempotent: revoking an already-revoked key returns
success. A cq platform should retain the API key record with a
revoked-at marker so the listing remains audit-friendly while the key
itself stops working immediately.

Pass the key's ID (not its prefix) as the positional argument. Find it
with cq auth key list.`

// newAuthKeyCmd returns the cq auth key parent command and its
// create, list, and revoke subcommands.
func newAuthKeyCmd(cfg authOptions) *cobra.Command {
	cmd := &cobra.Command{
		Use:   "key",
		Short: "Manage API keys for the authenticated user.",
		Long:  authKeyLongDoc,
	}

	cmd.AddCommand(newAuthKeyCreateCmd(cfg))
	cmd.AddCommand(newAuthKeyListCmd(cfg))
	cmd.AddCommand(newAuthKeyRevokeCmd(cfg))

	return cmd
}

// newAuthKeyCreateCmd returns the cq auth key create subcommand.
func newAuthKeyCreateCmd(cfg authOptions) *cobra.Command {
	var (
		name     string
		ttlInput string
		labels   []string
	)

	cmd := &cobra.Command{
		Use:   "create",
		Short: "Create a new API key.",
		Long:  authKeyCreateLongDoc,
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			// Args/flag validation has already run; anything from here
			// down is an operational failure where the usage banner only
			// adds noise, so suppress it for any error path below.
			cmd.SilenceUsage = true

			canonicalTTL, err := parseTTL(ttlInput)
			if err != nil {
				return err
			}

			client, jwt, err := authKeySetup(cfg)
			if err != nil {
				return err
			}

			created, err := client.CreateAPIKey(cmd.Context(), jwt, auth.CreateAPIKeyRequest{
				Name:   name,
				TTL:    canonicalTTL,
				Labels: labels,
			})
			if err != nil {
				return mapAuthKeyError(cmd, err)
			}

			renderCreatedKey(cmd.OutOrStdout(), cmd.ErrOrStderr(), created)

			return nil
		},
	}

	cmd.Flags().StringVar(&name, "name", "", "Display name for the key (required).")
	cmd.Flags().
		StringVar(&ttlInput, "ttl", "", "Lifetime in the format <integer><s|m|h|d>, e.g. 30d, 12h. Max 365d. Required.")
	cmd.Flags().
		StringSliceVar(&labels, "labels", nil, "Optional labels (repeat --labels or supply a comma-separated list).")

	_ = cmd.MarkFlagRequired("name")
	_ = cmd.MarkFlagRequired("ttl")

	return cmd
}

// newAuthKeyListCmd returns the cq auth key list subcommand.
func newAuthKeyListCmd(cfg authOptions) *cobra.Command {
	var asJSON bool

	cmd := &cobra.Command{
		Use:   "list",
		Short: "List your API keys.",
		Long:  authKeyListLongDoc,
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			cmd.SilenceUsage = true

			client, jwt, err := authKeySetup(cfg)
			if err != nil {
				return err
			}

			keys, err := client.ListAPIKeys(cmd.Context(), jwt)
			if err != nil {
				return mapAuthKeyError(cmd, err)
			}

			return renderKeyList(cmd.OutOrStdout(), cmd.ErrOrStderr(), keys, asJSON)
		},
	}

	cmd.Flags().BoolVar(&asJSON, "json", false, "Emit JSON instead of plain text.")

	return cmd
}

// newAuthKeyRevokeCmd returns the cq auth key revoke subcommand.
func newAuthKeyRevokeCmd(cfg authOptions) *cobra.Command {
	return &cobra.Command{
		Use:   "revoke <key-id>",
		Short: "Revoke an API key by its ID.",
		Long:  authKeyRevokeLongDoc,
		Args: func(_ *cobra.Command, args []string) error {
			if len(args) != 1 || strings.TrimSpace(args[0]) == "" {
				return errors.New(`key ID required. Run "cq auth key list" to find one`)
			}

			return nil
		},
		RunE: func(cmd *cobra.Command, args []string) error {
			cmd.SilenceUsage = true

			client, jwt, err := authKeySetup(cfg)
			if err != nil {
				return err
			}

			keyID := strings.TrimSpace(args[0])

			if err := client.RevokeAPIKey(cmd.Context(), jwt, keyID); err != nil {
				return mapAuthKeyError(cmd, err)
			}

			_, _ = fmt.Fprintf(cmd.ErrOrStderr(), "Revoked API key %s.\n", keyID)

			return nil
		},
	}
}

// authKeySetup resolves the platform address, opens the credential
// store, loads the session JWT, and builds the platform client. It
// centralises the prerequisites every auth key subcommand shares.
func authKeySetup(cfg authOptions) (auth.Client, string, error) {
	addr, err := requireAuthAddr()
	if err != nil {
		return nil, "", err
	}

	store, err := cfg.newStore()
	if err != nil {
		return nil, "", fmt.Errorf("opening credential store: %w", err)
	}

	creds, err := store.Load()
	if err != nil {
		if errors.Is(err, credstore.ErrNotFound) {
			return nil, "", errors.New(`not signed in. Run "cq auth login <provider>" first`)
		}

		return nil, "", fmt.Errorf("loading credentials: %w", err)
	}

	if creds.SessionJWT == "" {
		return nil, "", errors.New(`stored credentials missing session JWT. Run "cq auth login <provider>" again`)
	}

	return cfg.newClient(addr), creds.SessionJWT, nil
}

// formatKeyStatus returns a single-word status for the key suitable for
// table rendering. The platform-supplied IsExpired and IsActive fields
// are computed at response time, so we trust them rather than recomputing
// against the local clock.
func formatKeyStatus(k auth.APIKey) string {
	switch {
	case k.RevokedAt != nil:
		return "revoked"
	case k.IsExpired:
		return "expired"
	case k.IsActive:
		return "active"
	default:
		return "inactive"
	}
}

// formatLabels renders a key's labels for plain-text output. An empty
// list renders as "-" so columns line up.
func formatLabels(labels []string) string {
	if len(labels) == 0 {
		return "-"
	}

	return strings.Join(labels, ",")
}

// ttlEchoMax bounds how many bytes of the user-supplied --ttl value
// appear in any error message, so an attacker-controlled megabyte
// input cannot produce a megabyte error string in cobra output or
// logs. Matches the truncation budget in sdk/go/ttl.Parse.
const ttlEchoMax = 64

// parseTTL is a thin CLI-facing wrapper around ttl.Parse that maps the
// SDK's typed errors into --ttl-prefixed cobra messages. The SDK owns
// the canonical grammar, max bound, and case normalisation; this layer
// only reshapes errors so the user sees the flag name they typed.
func parseTTL(s string) (string, error) {
	canonical, _, err := ttl.Parse(s)
	// Truncate before quoting so the wrapper does not undo ttl.Parse's
	// own bounded-output guarantee for very long inputs.
	echo := s
	if len(echo) > ttlEchoMax {
		echo = echo[:ttlEchoMax]
	}
	switch {
	case errors.Is(err, ttl.ErrEmpty):
		return "", errors.New("--ttl is required: supply a value like 30d, 12h, 90d (max 365d)")
	case errors.Is(err, ttl.ErrGrammar):
		return "", fmt.Errorf("--ttl %q is not a valid duration: expected <integer><s|m|h|d>, e.g. 30d, 12h", echo)
	case errors.Is(err, ttl.ErrTooLarge):
		return "", fmt.Errorf("--ttl %q exceeds the maximum of 365d", echo)
	case errors.Is(err, ttl.ErrTooSmall):
		return "", fmt.Errorf("--ttl %q must be greater than zero", echo)
	case err != nil:
		return "", fmt.Errorf("--ttl %q: %w", echo, err)
	}

	return canonical, nil
}

// mapAuthKeyError turns a platform error into a user-friendly cobra
// error. The cmd is used to silence cobra's usage banner on the typed
// errors where it would only add noise.
func mapAuthKeyError(cmd *cobra.Command, err error) error {
	if errors.Is(err, auth.ErrSessionExpired) {
		cmd.SilenceUsage = true

		return errors.New(`session expired or invalid. Run "cq auth login <provider>" to sign in again`)
	}

	var capReached *auth.APIKeyLimitReachedError
	if errors.As(err, &capReached) {
		cmd.SilenceUsage = true

		if capReached.Detail != "" {
			return fmt.Errorf("cannot create key: %s", capReached.Detail)
		}

		return errors.New("cannot create key: active API key limit reached. Revoke a key first")
	}

	var notFound *auth.APIKeyNotFoundError
	if errors.As(err, &notFound) {
		cmd.SilenceUsage = true

		return fmt.Errorf("API key %s not found", notFound.KeyID)
	}

	var validation *auth.APIKeyValidationError
	if errors.As(err, &validation) {
		cmd.SilenceUsage = true

		if validation.Detail != "" {
			return fmt.Errorf("invalid request: %s", validation.Detail)
		}

		return errors.New("invalid request")
	}

	return err
}

// renderCreatedKey writes the create response: the API key to stdout
// (so a shell can capture it cleanly) and a human-readable banner to
// stderr.
func renderCreatedKey(stdout, stderr io.Writer, created auth.CreatedAPIKey) {
	_, _ = fmt.Fprintln(stdout, created.Token)

	expires := created.ExpiresAt.UTC().Format(time.RFC3339)
	labels := formatLabels(created.Labels)
	_, _ = fmt.Fprintf(stderr,
		"Created API key '%s' (id=%s prefix=%s labels=%s expires=%s).\n"+
			"The API key above is shown only once. Save it now (e.g. export CQ_API_KEY=...).\n",
		created.Name, created.ID, created.Prefix, labels, expires,
	)
}

// renderKeyList writes the list response in either plain text or JSON.
// Plain text is one row per key with id, prefix, status, expiry, name,
// and labels. The empty-list message is written to stderr so a script
// capturing stdout (e.g. KEYS=$(cq auth key list)) sees an empty
// string in the no-keys case rather than a sentinel "No API keys."
// line that callers would otherwise have to special-case.
func renderKeyList(stdout, stderr io.Writer, keys []auth.APIKey, asJSON bool) error {
	if asJSON {
		enc := json.NewEncoder(stdout)
		enc.SetIndent("", jsonIndent)

		// Emit a stable envelope so jq users can rely on the shape
		// regardless of how the platform wraps its response.
		return enc.Encode(struct {
			Data  []auth.APIKey `json:"data"`
			Count int           `json:"count"`
		}{Data: keys, Count: len(keys)})
	}

	if len(keys) == 0 {
		_, _ = fmt.Fprintln(stderr, "No API keys.")

		return nil
	}

	for _, k := range keys {
		_, _ = fmt.Fprintf(stdout, "%s\t%s\t%s\t%s\t%s\t%s\n",
			k.ID,
			k.Prefix,
			formatKeyStatus(k),
			k.ExpiresAt.UTC().Format(time.RFC3339),
			k.Name,
			formatLabels(k.Labels),
		)
	}

	return nil
}
