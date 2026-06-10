package auth

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"time"

	"github.com/mozilla-ai/cq/cli/internal/credstore"
)

// loginListenerTimeout is how long the loopback listener waits for the
// browser callback before giving up. Sized well below the platform's
// oauth_pending_state expiry so we surface a clearer error than the
// server's "state expired" message.
const loginListenerTimeout = 5 * time.Minute

// LoginConfig gathers the configuration and dependencies Login needs
// to run an interactive sign-in. Provider, Client, Store, and In are
// strictly required; the other fields default to sensible production
// values when zero.
type LoginConfig struct {
	// Provider is the machine-readable OAuth provider name. Empty is
	// rejected up front with ErrProviderRequired; unknown values reach
	// the platform and surface whatever message it returns.
	Provider string

	// Client is the platform HTTP client.
	Client Client

	// Store persists the resulting session JWT and identity.
	Store credstore.Store

	// In is the source of interactive input during the sign-in prompt
	// and onboarding.
	In io.Reader

	// Out is the destination for status and onboarding prompts.
	// Defaults to io.Discard when nil.
	Out io.Writer

	// OpenBrowser, when non-nil, is used in place of the package's
	// default browser launcher. Tests inject a stub that drives the
	// loopback listener directly.
	OpenBrowser func(url string) error

	// Timeout overrides the loopback listener wait. Zero uses
	// loginListenerTimeout.
	Timeout time.Duration
}

// Login runs the full interactive OAuth flow: prompt before launching
// the browser, generate a PKCE pair, bind a loopback listener, ask
// the platform for an authorization URL, open the browser, wait for
// the callback, exchange the code for a session JWT, fetch the user
// profile, run the onboarding loop when needed, and finally persist
// the result to Store.
//
// The function returns nil on a clean sign-in, ErrProviderRequired
// when no provider is supplied, or an error describing the first step
// that failed. Storage is updated only after every platform
// interaction succeeds.
func Login(ctx context.Context, c LoginConfig) error {
	if c.Client == nil {
		return errors.New("auth: Login requires Client")
	}

	if c.Store == nil {
		return errors.New("auth: Login requires Store")
	}

	if c.In == nil {
		return errors.New("auth: Login requires In for interactive prompts")
	}

	if c.Provider == "" {
		return ErrProviderRequired
	}

	out := c.Out
	if out == nil {
		out = io.Discard
	}

	openBrowserFn := c.OpenBrowser
	if openBrowserFn == nil {
		openBrowserFn = openBrowser
	}

	timeout := c.Timeout
	if timeout == 0 {
		timeout = loginListenerTimeout
	}

	pk, err := newPKCE()
	if err != nil {
		return err
	}

	listener, err := startListener()
	if err != nil {
		return fmt.Errorf("starting loopback listener: %w", err)
	}
	defer func() { _ = listener.Close() }()

	authorizationURL, err := c.Client.OAuthNativeStart(ctx, NativeStartRequest{
		Provider:      c.Provider,
		CodeChallenge: pk.challenge,
		RedirectURI:   listener.URL(),
	})
	if err != nil {
		return fmt.Errorf("starting OAuth flow: %w", err)
	}

	// One scanner shared between the press-Enter prompt and the
	// onboarding-username prompt so input from c.In is buffered in
	// exactly one place.
	scanner := bufio.NewScanner(c.In)

	if err := promptToOpenBrowser(scanner, out, authorizationURL, openBrowserFn); err != nil {
		return err
	}

	waitCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	exchangeCode, err := listener.Wait(waitCtx)
	if err != nil {
		if errors.Is(err, context.DeadlineExceeded) {
			return errors.New("sign-in didn't complete in time")
		}

		return fmt.Errorf("waiting for sign-in callback: %w", err)
	}

	jwt, err := c.Client.OAuthNativeExchange(ctx, NativeExchangeRequest{
		ExchangeCode: exchangeCode,
		CodeVerifier: pk.verifier,
	})
	if err != nil {
		return fmt.Errorf("exchanging code for token: %w", err)
	}

	user, err := c.Client.Me(ctx, jwt)
	if err != nil {
		return fmt.Errorf("fetching user profile: %w", err)
	}

	if user.Username == "" {
		_, _ = fmt.Fprintln(out, "Choose a username to finish setting up your account.")

		user, err = claimUsernameInteractively(ctx, scanner, out, c.Client, jwt)
		if err != nil {
			return err
		}
	}

	if err := c.Store.Save(credstore.Credentials{
		SessionJWT: jwt,
		Username:   user.Username,
	}); err != nil {
		return fmt.Errorf("saving credentials: %w", err)
	}

	_, _ = fmt.Fprintf(out, "Signed in as %s.\n", user.Username)

	return nil
}

// claimUsernameInteractively loops on the user's input, sending each
// candidate to ClaimUsername, re-prompting on platform-side validation
// errors (409 unavailable, 422 invalid format) and propagating
// rate-limit and unrecoverable errors to the caller.
func claimUsernameInteractively(
	ctx context.Context,
	scanner *bufio.Scanner,
	out io.Writer,
	client Client,
	jwt string,
) (User, error) {
	for {
		username, err := readUsername(scanner, out)
		if err != nil {
			return User{}, err
		}

		user, err := client.ClaimUsername(ctx, jwt, username)
		if err == nil {
			return user, nil
		}

		var unavailable *UsernameUnavailableError
		if errors.As(err, &unavailable) {
			renderUnavailable(out, username, unavailable.Suggestions)

			continue
		}

		var formatErr *UsernameFormatError
		if errors.As(err, &formatErr) {
			renderInvalidFormat(out, username, formatErr.Detail)

			continue
		}

		// Rate-limit and any other error: surface to the caller.
		// Looping against rate limits would only deepen the limit
		// window.
		return User{}, err
	}
}

// promptToOpenBrowser shows the authorization URL and waits for the
// user to press Enter before launching the browser. If the launch
// fails, the URL is repeated so the user can paste it manually. EOF
// before Enter is treated as a cancelled sign-in.
func promptToOpenBrowser(
	scanner *bufio.Scanner,
	out io.Writer,
	authorizationURL string,
	openBrowserFn func(string) error,
) error {
	_, _ = fmt.Fprintf(out, "Sign in at: %s\n", authorizationURL)
	_, _ = fmt.Fprintln(out, "Press Enter to open this URL in your browser, or open it yourself.")

	if !scanner.Scan() {
		if err := scanner.Err(); err != nil {
			return fmt.Errorf("waiting for confirmation: %w", err)
		}

		return errors.New("sign-in cancelled (no confirmation received)")
	}

	if err := openBrowserFn(authorizationURL); err != nil {
		_, _ = fmt.Fprintf(out, "Couldn't open browser automatically. Visit the URL above manually.\n")
	}

	return nil
}
