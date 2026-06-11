package auth

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"fmt"
	"net"
	"net/http"
	"regexp"
	"sync"
	"time"

	_ "embed"
)

const (
	// callbackPrefix is the static prefix of the loopback callback path.
	// The full path served per listener is callbackPrefix + a random
	// token generated at startListener time, so a same-host process
	// cannot race the redirect by guessing the path.
	callbackPrefix = "/cb/"

	// callbackShutdownGrace is the time the listener spends draining the
	// success-page response before shutting down its server.
	callbackShutdownGrace = 500 * time.Millisecond

	// callbackTokenBytes is the number of random bytes drawn for the
	// per-listener callback token. 16 bytes encode to 22 base64url
	// characters (no padding), placing the entropy floor at ~128 bits
	// and matching the lower bound the platform validator accepts.
	callbackTokenBytes = 16
)

// callbackPathPattern is the shape the loopback callback path must
// take: the static callbackPrefix followed by a URL-safe random token
// of 22-64 characters. The platform's redirect_uri validator enforces
// the same regex; carrying it in CLI code lets startListener fail fast
// if the token length is ever changed in a way the platform would
// reject, rather than surfacing as a sign-in failure at exchange time.
var callbackPathPattern = regexp.MustCompile(`^/cb/[A-Za-z0-9_-]{22,64}$`)

// callbackSuccessPage is the HTML returned to the browser after a
// successful callback. The content lives in callback_success.html so
// styling and copy can evolve without touching this file.
//
//go:embed callback_success.html
var callbackSuccessPage string

// callbackErrorPage is the HTML returned to the browser when the
// provider redirected with an error or the callback was malformed. It
// keeps the user from staring at a "you're signed in" page while the
// CLI is reporting failure.
//
//go:embed callback_error.html
var callbackErrorPage string

// callbackResult is the outcome captured from the OAuth provider's
// redirect: either a non-empty exchangeCode (success) or err (failure).
type callbackResult struct {
	exchangeCode string
	err          error
}

// listener is a single-shot HTTP listener bound to an ephemeral port
// on the loopback interface. It accepts exactly one callback on
// callbackPrefix + a per-instance random token, and stores the
// captured result for Wait().
type listener struct {
	server *http.Server
	addr   string
	path   string

	once   sync.Once
	result chan callbackResult
}

// startListener binds to an ephemeral port on the loopback interface,
// starts serving, and returns a listener ready to receive a single
// OAuth callback. The caller must call Close() to release the port.
func startListener() (*listener, error) {
	tokenBytes := make([]byte, callbackTokenBytes)
	if _, err := rand.Read(tokenBytes); err != nil {
		return nil, fmt.Errorf("generating callback token: %w", err)
	}

	path := callbackPrefix + base64.RawURLEncoding.EncodeToString(tokenBytes)
	if !callbackPathPattern.MatchString(path) {
		return nil, fmt.Errorf("generated callback path '%s' does not match expected pattern", path)
	}

	// RFC 8252 §7.3: native OAuth clients should bind to the loopback
	// IP literal rather than "localhost". On dual-stack hosts
	// "localhost" can resolve to ::1, which would not match a 127.0.0.1
	// socket. Port 0 asks the OS to pick an ephemeral port (always
	// non-privileged).
	netListener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return nil, fmt.Errorf("binding loopback listener: %w", err)
	}

	l := &listener{
		addr:   netListener.Addr().String(),
		path:   path,
		result: make(chan callbackResult, 1),
	}

	mux := http.NewServeMux()
	mux.HandleFunc(l.path, l.handle)

	l.server = &http.Server{
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		err := l.server.Serve(netListener)
		// http.ErrServerClosed is the expected outcome of Close().
		// Anything else (file descriptor exhaustion, accept failure
		// after a TOCTOU race, etc.) needs to surface to Wait so the
		// caller does not block until its context expires.
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			l.once.Do(func() {
				l.result <- callbackResult{err: fmt.Errorf("loopback listener: %w", err)}
			})
		}
	}()

	return l, nil
}

// Close shuts the underlying HTTP server down, releasing the bound port.
// Safe to call multiple times.
func (l *listener) Close() error {
	ctx, cancel := context.WithTimeout(context.Background(), callbackShutdownGrace)
	defer cancel()

	return l.server.Shutdown(ctx)
}

// URL returns the absolute URL the OAuth provider should redirect to.
//
// The plain http scheme is correct per RFC 8252 §8.3: loopback traffic
// never leaves the host, so encryption adds no security and a
// self-signed cert would only introduce a browser trust prompt. The
// confidentiality boundary is the PKCE code_verifier held only in this
// process.
func (l *listener) URL() string {
	return "http://" + l.addr + l.path
}

// Wait blocks until either an OAuth callback is captured, the supplied
// context fires, or the listener is closed. After the first valid
// callback all subsequent traffic is ignored.
func (l *listener) Wait(ctx context.Context) (string, error) {
	select {
	case res := <-l.result:
		return res.exchangeCode, res.err
	case <-ctx.Done():
		return "", ctx.Err()
	}
}

// handle is the only HTTP handler registered, scoped to the listener's
// tokenised callback path. Subsequent calls after the first are ignored
// to satisfy the single-shot contract.
//
// The HTTP response mirrors the parsed result: a 200 success page when
// the provider redirected with an exchange_code, and a 400 error page
// when it redirected with "error=" or omitted both. Without the split,
// the user would see "signed in" in the browser while the CLI reports
// a failure in the terminal.
func (l *listener) handle(w http.ResponseWriter, r *http.Request) {
	result := parseCallback(r)

	delivered := false

	l.once.Do(func() {
		l.result <- result
		delivered = true
	})

	if !delivered {
		http.Error(w, "callback already received", http.StatusGone)

		return
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")

	if result.err != nil {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte(callbackErrorPage))

		return
	}

	_, _ = w.Write([]byte(callbackSuccessPage))
}

// parseCallback extracts the result from the redirect query string.
// The OAuth provider supplies either "exchange_code=..." (success) or
// "error=...&error_description=..." (failure).
func parseCallback(r *http.Request) callbackResult {
	q := r.URL.Query()

	if code := q.Get("exchange_code"); code != "" {
		return callbackResult{exchangeCode: code}
	}

	if errCode := q.Get("error"); errCode != "" {
		desc := q.Get("error_description")
		if desc == "" {
			return callbackResult{err: fmt.Errorf("oauth provider returned error: '%s'", errCode)}
		}

		return callbackResult{err: fmt.Errorf("oauth provider returned error: '%s': %s", errCode, desc)}
	}

	return callbackResult{err: errors.New("oauth callback missing exchange_code and error")}
}
