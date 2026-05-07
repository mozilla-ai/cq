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
// The interface holds five methods, more than the typical "small
// interface" Go ideal. They are kept together because they form a
// cohesive auth-control-plane surface with a single in-package
// consumer (the Login orchestration); splitting into a ProviderLister
// + OAuthClient + UserClient triad would add indirection without
// reducing coupling, since every call site already needs all three.
type Client interface {
	// ClaimUsername sets the user's username. Returns
	// *UsernameUnavailableError, *UsernameFormatError,
	// ErrUsernameAlreadySet, or *RateLimitedError on the typed failure
	// modes.
	ClaimUsername(ctx context.Context, jwt, username string) (User, error)

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
