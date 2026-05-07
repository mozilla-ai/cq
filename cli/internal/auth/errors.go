package auth

import (
	"errors"
	"fmt"
	"time"
)

// ErrInvalidGrant is returned by the exchange step when the platform
// rejects the exchange code or PKCE verifier. The platform deliberately
// collapses unknown-code, wrong-verifier, and replay into one wire
// response, so callers cannot distinguish among them.
var ErrInvalidGrant = errors.New("auth: invalid grant")

// ErrProviderRequired is returned by Login when the supplied
// configuration does not name an OAuth provider. The internal package
// stays out of the business of suggesting CLI commands; callers
// (typically the cobra layer) translate this into a user-facing
// "run cq auth providers" hint.
var ErrProviderRequired = errors.New("auth: provider required")

// ErrUsernameAlreadySet is returned by ClaimUsername when the user has
// previously claimed a username and the server refuses a second claim.
var ErrUsernameAlreadySet = errors.New("auth: username already set")

// RateLimitedError is returned when the platform applies a 429 to a
// request. RetryAfter is the duration the server suggests waiting
// before retrying, parsed from the Retry-After header. Zero when the
// header is absent or unparseable.
type RateLimitedError struct {
	// RetryAfter is the suggested wait duration. May be zero.
	RetryAfter time.Duration
}

// Error implements the error interface.
func (e *RateLimitedError) Error() string {
	if e.RetryAfter == 0 {
		return "auth: rate limited"
	}

	return fmt.Sprintf("auth: rate limited, retry after %s", e.RetryAfter)
}

// UsernameFormatError is returned by ClaimUsername when the requested
// username fails server-side format validation. Detail is the
// human-readable explanation supplied by the platform.
type UsernameFormatError struct {
	// Detail is the server-supplied human-readable explanation.
	Detail string
}

// Error implements the error interface.
func (e *UsernameFormatError) Error() string {
	if e.Detail == "" {
		return "auth: username invalid format"
	}

	return "auth: username invalid format: " + e.Detail
}

// UsernameUnavailableError is returned by ClaimUsername when the
// requested username is reserved or already taken. Suggestions is the
// server-supplied list of available alternatives.
type UsernameUnavailableError struct {
	// Suggestions are server-side alternatives the caller can offer the
	// user. May be empty if the server returned none.
	Suggestions []string
}

// Error implements the error interface.
func (e *UsernameUnavailableError) Error() string {
	return "auth: username unavailable"
}
