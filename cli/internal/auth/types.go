package auth

// NativeExchangeRequest carries the inputs required to redeem a
// one-time exchange code, captured by the loopback callback, for a
// session JWT.
type NativeExchangeRequest struct {
	// ExchangeCode is the one-time code received via the loopback callback.
	ExchangeCode string `json:"exchange_code"`

	// CodeVerifier is the PKCE verifier kept by the client throughout the
	// flow. Released only at the exchange step.
	CodeVerifier string `json:"code_verifier"`
}

// NativeStartRequest carries the inputs needed to begin a
// browser-based OIDC sign-in: the chosen provider, the PKCE
// challenge, and the loopback URL the platform should redirect the
// browser to once authentication completes.
type NativeStartRequest struct {
	// Provider is the machine-readable provider identifier.
	Provider string `json:"provider"`

	// CodeChallenge is the base64url-encoded SHA-256 of the PKCE verifier
	// (43 characters, no padding).
	CodeChallenge string `json:"code_challenge"`

	// RedirectURI is the loopback URL the browser should be redirected to
	// after the authorization step completes.
	RedirectURI string `json:"redirect_uri"`
}

// Provider describes a single OAuth provider exposed by the platform.
type Provider struct {
	// Name is the machine-readable identifier (e.g. "github", "google").
	Name string `json:"name"`

	// DisplayName is the human-readable label (e.g. "GitHub", "Google").
	DisplayName string `json:"display_name"`

	// Enabled is true when the provider is configured for sign-in.
	Enabled bool `json:"enabled"`
}

// User is the public-facing user identity returned by the platform.
type User struct {
	// ID is the platform's UUID for the user.
	ID string `json:"id"`

	// Email is the user's verified email address.
	Email string `json:"email"`

	// FullName is the user's display name from the OAuth provider.
	FullName string `json:"full_name"`

	// Username is the chosen platform username. Empty when the user has
	// not yet claimed one (the onboarding gate during initial sign-in).
	Username string `json:"username"`

	// OAuthProvider names the provider used to sign in (e.g. "github").
	// Empty for users that pre-date the OAuth-only auth path.
	OAuthProvider string `json:"oauth_provider"`
}
