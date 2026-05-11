package auth

import (
	"context"
	"net/http"
	"time"
)

// httpDefaultTimeout caps a single platform HTTP call. Individual
// invocations may shorten the deadline by passing a context with a
// stricter timeout.
const httpDefaultTimeout = 30 * time.Second

// Client is the platform HTTP surface required by the auth flow.
// Implementations must be safe to share across the methods of a single
// login invocation; concurrent use across goroutines is not required.
//
// JWT-bearing methods take the token as an explicit parameter so the
// Client itself stays stateless and easier to mock.
//
// The interface holds the methods that make up the auth control plane:
// OAuth sign-in, identity, and per-user API key management. They live
// behind one type because every call site uses the same baseURL and
// transport; splitting them into separate interfaces would force a
// matching split at every consumer without reducing coupling.
type Client interface {
	// ClaimUsername sets the user's username. Returns
	// *UsernameUnavailableError, *UsernameFormatError,
	// ErrUsernameAlreadySet, or *RateLimitedError on the typed failure
	// modes.
	ClaimUsername(ctx context.Context, jwt, username string) (User, error)

	// CreateAPIKey provisions a new API key for the authenticated user
	// and returns the API key value exactly once. Returns
	// ErrSessionExpired (401), *APIKeyLimitReachedError (409), or
	// *APIKeyValidationError (422) on the typed failure modes.
	CreateAPIKey(ctx context.Context, jwt string, req CreateAPIKeyRequest) (CreatedAPIKey, error)

	// ListAPIKeys returns the authenticated user's API keys. Revoked
	// and expired keys are included so callers can render audit
	// history. Returns ErrSessionExpired (401) when the JWT is invalid.
	ListAPIKeys(ctx context.Context, jwt string) ([]APIKey, error)

	// Me returns the user identity associated with the supplied JWT.
	Me(ctx context.Context, jwt string) (User, error)

	// OAuthNativeExchange redeems a one-time exchange code for a session
	// JWT. Returns ErrInvalidGrant when the platform rejects the grant.
	OAuthNativeExchange(ctx context.Context, req NativeExchangeRequest) (accessToken string, err error)

	// OAuthNativeStart begins a native OIDC flow and returns the URL the
	// browser should be sent to.
	OAuthNativeStart(ctx context.Context, req NativeStartRequest) (authorizationURL string, err error)

	// OAuthProviders returns the providers configured on the platform.
	OAuthProviders(ctx context.Context) ([]Provider, error)

	// RevokeAPIKey marks the named key revoked. The operation is
	// idempotent: revoking an already-revoked key still returns nil.
	// Returns ErrSessionExpired (401) or *APIKeyNotFoundError (404) on
	// the typed failure modes.
	RevokeAPIKey(ctx context.Context, jwt string, keyID string) error
}

// NewClient returns a Client that talks to the platform at baseURL.
// baseURL must not include a trailing /api/v1 path; the client appends
// the version prefix itself.
func NewClient(baseURL string) Client {
	return &httpClient{
		baseURL: baseURL,
		http:    &http.Client{Timeout: httpDefaultTimeout},
	}
}
