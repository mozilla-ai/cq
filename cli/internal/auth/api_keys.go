package auth

import "time"

// APIKey is the public projection of a stored API key. It never
// carries the API key itself; the API key is returned exactly once,
// on CreatedAPIKey, and never persisted server-side.
type APIKey struct {
	// ID is the platform's UUID for the key.
	ID string `json:"id"`

	// Name is the user-supplied display name for the key.
	Name string `json:"name"`

	// Labels is the user-supplied list of free-form labels. Always
	// non-nil after a successful round-trip; the platform decodes a
	// missing field as the empty list.
	Labels []string `json:"labels"`

	// Prefix is the first eight characters of the API key, captured
	// at creation time and shown in listings to help users identify a
	// key without exposing the full value.
	Prefix string `json:"key_prefix"`

	// TTL is the requested time-to-live in the canonical platform
	// duration grammar (e.g. "30d", "12h").
	TTL string `json:"ttl"`

	// ExpiresAt is the absolute time at which the platform will refuse
	// the key, regardless of revocation state.
	ExpiresAt time.Time `json:"expires_at"`

	// CreatedAt is the creation timestamp.
	CreatedAt time.Time `json:"created_at"`

	// LastUsedAt is the most recent successful authentication with the
	// key. Nil until first use.
	LastUsedAt *time.Time `json:"last_used_at,omitempty"`

	// RevokedAt is the time the key was revoked. Nil while the key is
	// still active.
	RevokedAt *time.Time `json:"revoked_at,omitempty"`

	// IsExpired is the platform-computed comparison of ExpiresAt against
	// the server's wall clock at response time. Clients must not cache
	// it as durable state.
	IsExpired bool `json:"is_expired"`

	// IsActive is true when the key has not been revoked and has not yet
	// expired. Clients must not cache it as durable state.
	IsActive bool `json:"is_active"`
}

// CreateAPIKeyRequest carries the inputs required to create a new API
// key. Labels is optional; the platform normalises the list (trims,
// drops empties, deduplicates) before persisting it.
type CreateAPIKeyRequest struct {
	// Name is the display name. Required, 1-64 characters after trimming.
	Name string `json:"name"`

	// TTL is the time-to-live in the platform's duration grammar
	// (^\d+[smhd]$). Required.
	TTL string `json:"ttl"`

	// Labels is the optional list of free-form labels.
	Labels []string `json:"labels,omitempty"`
}

// CreatedAPIKey is the response returned exactly once when an API key
// is created. The Token field carries the API key value; this is the
// only opportunity for the client to capture it.
type CreatedAPIKey struct {
	APIKey

	// Token is the API key value (cqa.v1.<id>.<secret>). The platform
	// never returns it again.
	Token string `json:"api_key"` // pragma: allowlist secret
}
