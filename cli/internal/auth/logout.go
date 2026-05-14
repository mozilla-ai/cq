package auth

import (
	"context"
	"errors"
	"fmt"
	"io"

	"github.com/mozilla-ai/cq/cli/internal/credstore"
)

// LogoutConfig gathers the inputs to Logout.
type LogoutConfig struct {
	// Store is the credstore to clear.
	Store credstore.Store

	// Client is the platform HTTP client. Required only when Revoke is
	// true.
	Client Client

	// Revoke asks the platform to invalidate the current session before
	// local credentials are deleted.
	Revoke bool

	// AllDevices requests server-side revocation across every device.
	// Ignored unless Revoke is true.
	AllDevices bool

	// Out receives the user-facing acknowledgement. Defaults to
	// io.Discard when nil.
	Out io.Writer
}

// Logout clears locally-stored session credentials.
//
// When Revoke is true, Logout first asks the platform to invalidate the
// current session, then clears local credentials. Non-401 revocation
// failures leave local credentials untouched so the user can retry.
func Logout(ctx context.Context, p LogoutConfig) error {
	out := p.Out
	if out == nil {
		out = io.Discard
	}

	clearAndReport := func(msg string) error {
		if err := p.Store.Delete(); err != nil {
			return fmt.Errorf("clearing credentials: %w", err)
		}

		_, _ = fmt.Fprintln(out, msg)

		return nil
	}

	if !p.Revoke {
		return clearAndReport("Signed out (local credentials cleared).")
	}

	creds, err := p.Store.Load()
	if err != nil {
		if errors.Is(err, credstore.ErrNotFound) {
			_, _ = fmt.Fprintln(out, "Signed out (local credentials already absent).")

			return nil
		}

		return fmt.Errorf("loading credentials: %w", err)
	}

	if creds.SessionJWT == "" {
		return clearAndReport("Signed out (local credentials cleared).")
	}

	if p.Client == nil {
		return errors.New("auth: Logout with Revoke requires Client")
	}

	err = p.Client.Logout(ctx, creds.SessionJWT, p.AllDevices)
	if err != nil {
		if errors.Is(err, ErrSessionExpired) {
			return clearAndReport("Signed out locally. Session was already expired or invalid, so server revocation could not be confirmed.")
		}

		return fmt.Errorf("revoking server session: %w", err)
	}

	if p.AllDevices {
		return clearAndReport("Signed out (server session revoked on all devices; local credentials cleared).")
	}

	return clearAndReport("Signed out (server session revoked; local credentials cleared).")
}
