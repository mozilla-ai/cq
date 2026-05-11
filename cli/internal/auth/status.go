package auth

import (
	"context"
	"errors"
	"fmt"
	"io"
	"time"

	"github.com/mozilla-ai/cq/cli/internal/credstore"
)

// StatusConfig gathers the inputs to Status.
type StatusConfig struct {
	// Store loads the persisted credentials.
	Store credstore.Store

	// Server is the effective platform URL (from --addr / CQ_ADDR /
	// default), shown to the user for context.
	Server string

	// Out receives the rendered status output. Defaults to io.Discard
	// when nil.
	Out io.Writer
}

// Status prints the current auth state to Out. It returns
// credstore.ErrNotFound when no credentials are stored so the cobra
// layer can exit non-zero for shell scripts that gate on sign-in.
//
// Status is intentionally local-only: it does not contact the platform
// to verify the JWT. The session's actual validity is observed when
// the user runs a control-plane command.
func Status(_ context.Context, p StatusConfig) error {
	out := p.Out
	if out == nil {
		out = io.Discard
	}

	creds, err := p.Store.Load()
	if err != nil {
		if errors.Is(err, credstore.ErrNotFound) {
			_, _ = fmt.Fprintln(out, `Not signed in. Run "cq auth login <provider>" to sign in.`)

			return err
		}

		return fmt.Errorf("loading credentials: %w", err)
	}

	if p.Server != "" {
		_, _ = fmt.Fprintf(out, "Server:    %s\n", p.Server)
	}

	_, _ = fmt.Fprintf(out, "Signed in: %s\n", creds.Username)

	if !creds.SessionExpiresAt.IsZero() {
		_, _ = fmt.Fprintf(out, "Expires:   %s\n", creds.SessionExpiresAt.Format(time.RFC3339))
	}

	return nil
}
