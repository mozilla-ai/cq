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

// ErrLogoutUnsupported is returned by Logout when the configured
// platform does not expose the logout endpoint.
var ErrLogoutUnsupported = errors.New("auth: server-side logout unsupported")

// ErrSessionExpired is returned by JWT-bearing methods when the
// platform refuses the supplied token (HTTP 401). The CLI surfaces this
// to users as a hint to re-run cq auth login. The error deliberately
// collapses missing-token, malformed-token, and expired-token responses
// into one signal because the platform does not distinguish among them
// on the wire.
var ErrSessionExpired = errors.New("auth: session expired or invalid")

// ErrUsernameAlreadySet is returned by ClaimUsername when the user has
// previously claimed a username and the server refuses a second claim.
var ErrUsernameAlreadySet = errors.New("auth: username already set")

// APIKeyLimitReachedError is returned by CreateAPIKey when the user
// already holds the platform's maximum number of active keys (HTTP 409).
type APIKeyLimitReachedError struct {
	// Detail is the human-readable explanation supplied by the platform.
	Detail string
}

// Error implements the error interface.
func (e *APIKeyLimitReachedError) Error() string {
	if e.Detail == "" {
		return "auth: active API key limit reached"
	}

	return "auth: active API key limit reached: " + e.Detail
}

// APIKeyNotFoundError is returned by RevokeAPIKey when the requested
// key does not exist or is owned by a different user (HTTP 404). The
// platform deliberately collapses both into one response to avoid
// leaking key existence across users.
type APIKeyNotFoundError struct {
	// KeyID is the identifier the caller supplied. Echoed back so the
	// CLI can render a useful error message without re-threading the
	// argument.
	KeyID string
}

// Error implements the error interface.
func (e *APIKeyNotFoundError) Error() string {
	if e.KeyID == "" {
		return "auth: API key not found"
	}

	return "auth: API key '" + e.KeyID + "' not found"
}

// APIKeyValidationError is returned by CreateAPIKey when the platform
// rejects the request body (HTTP 422), typically for an invalid TTL,
// out-of-range name length, or too many labels.
type APIKeyValidationError struct {
	// Detail is the platform-supplied explanation. May be empty.
	Detail string
}

// Error implements the error interface.
func (e *APIKeyValidationError) Error() string {
	if e.Detail == "" {
		return "auth: API key request invalid"
	}

	return "auth: API key request invalid: " + e.Detail
}

// PlatformStatusError is returned for any non-2xx HTTP response that
// does not match a more specific typed error in mapError. It carries
// the status code so callers can post-process specific codes (for
// example, RevokeAPIKey wrapping a 404 with the requested key ID)
// without resorting to error-string matching.
type PlatformStatusError struct {
	// StatusCode is the HTTP status returned by the platform.
	StatusCode int

	// Detail is the parsed "detail" field from the JSON error body, if
	// present. Empty when the body did not carry that field.
	Detail string

	// Errored is the parsed "error" discriminator from the JSON error
	// body, if present. Empty when the body did not carry that field.
	Errored string

	// Body is the raw response body, capped at the platform error-body
	// byte limit. Used as the fallback explanation when Detail and
	// Errored are both empty.
	Body string
}

// Error implements the error interface.
func (e *PlatformStatusError) Error() string {
	switch {
	case e.Errored != "":
		return fmt.Sprintf("platform returned %d: '%s'", e.StatusCode, e.Errored)
	case e.Detail != "":
		return fmt.Sprintf("platform returned %d: %s", e.StatusCode, e.Detail)
	default:
		return fmt.Sprintf("platform returned %d: %s", e.StatusCode, e.Body)
	}
}

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
