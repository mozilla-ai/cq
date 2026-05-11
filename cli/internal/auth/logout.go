package auth

import (
	"context"
	"fmt"
	"io"

	"github.com/mozilla-ai/cq/cli/internal/credstore"
)

// LogoutConfig gathers the inputs to Logout.
type LogoutConfig struct {
	// Store is the credstore to clear.
	Store credstore.Store

	// Out receives the user-facing acknowledgement. Defaults to
	// io.Discard when nil.
	Out io.Writer
}

// Logout removes any locally-stored session credentials.
//
// Logout is currently local-only: server-side session revocation is
// tracked separately. A --revoke flag will be added once the platform
// exposes a logout endpoint.
func Logout(_ context.Context, p LogoutConfig) error {
	out := p.Out
	if out == nil {
		out = io.Discard
	}

	if err := p.Store.Delete(); err != nil {
		return fmt.Errorf("clearing credentials: %w", err)
	}

	_, _ = fmt.Fprintln(out, "Signed out (local credentials cleared).")

	return nil
}
