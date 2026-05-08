package credstore

import (
	"errors"
	"time"
)

// ErrNotFound is returned by Store.Load when no credentials are stored.
var ErrNotFound = errors.New("credstore: no credentials stored")

// Store persists Credentials. Implementations are not required to be safe for
// concurrent use; the CLI uses a single instance per command invocation.
type Store interface {
	// Delete removes any stored credentials. Returns nil if no credentials
	// were stored.
	Delete() error

	// Load returns the stored credentials, or ErrNotFound if none exist.
	Load() (Credentials, error)

	// Save persists creds, replacing any existing record.
	Save(creds Credentials) error
}

// Credentials is the persisted session state for a logged-in user.
type Credentials struct {
	// SessionJWT is the OIDC session token issued by the platform. Required.
	SessionJWT string `json:"session_jwt"`

	// SessionExpiresAt is the JWT expiry as reported by the server. Zero
	// when the server did not include an expiry; treated as "unknown".
	SessionExpiresAt time.Time `json:"session_expires_at,omitzero"`

	// Username is the platform-side username at the time of last login,
	// cached so "cq auth status" can render identity without a network call.
	Username string `json:"username"`
}

// New returns a Store backed by the OS keyring when reachable, falling
// back to a chmod-600 file under fileDir when it is not (for example,
// headless Linux without a running D-Bus session). The caller is
// responsible for resolving fileDir from whatever configuration source
// it owns; credstore deals only with storage.
//
// Selection happens once at construction time. The returned Store does
// not silently switch backends mid-process if keyring availability
// changes.
func New(fileDir string) (Store, error) {
	if keyringHealthy() {
		return newKeyringStore(), nil
	}

	return newFileStore(fileDir)
}
