package credstore

import (
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/zalando/go-keyring"
)

const (
	// keyringAccount is the account identifier paired with keyringService.
	// cq stores at most one record at a time, so a fixed value is enough.
	keyringAccount = "default"

	// keyringHealthAccount is the account identifier paired with
	// keyringHealthService.
	keyringHealthAccount = "probe"

	// keyringHealthService is the service identifier of the probe key used
	// to detect whether the keyring backend is reachable. The probe is
	// Get-only, so no entry is ever created in the user's keyring.
	keyringHealthService = "cq-health-probe"

	// keyringService is the service identifier under which cq stores its
	// credential record in the OS keyring.
	keyringService = "cq"

	// keyringTimeout caps a single keyring operation. Some backends can
	// hang in the underlying syscall (notably D-Bus on WSL); the cap
	// surfaces a clear error rather than blocking indefinitely.
	keyringTimeout = 3 * time.Second
)

// errKeyringTimeout is returned when a keyring operation exceeds its timeout.
var errKeyringTimeout = errors.New("credstore: keyring operation timed out")

// Compile-time assertion that *keyringStore satisfies Store.
var _ Store = (*keyringStore)(nil)

// keyringStore persists Credentials in the OS-native keyring (Keychain on
// macOS, Secret Service on Linux, Credential Manager on Windows). Calls are
// wrapped with keyringTimeout to defend against platform-specific hangs.
type keyringStore struct{}

// newKeyringStore returns a Store backed by the OS keyring.
func newKeyringStore() *keyringStore {
	return &keyringStore{}
}

// Delete removes the stored credentials. Returns nil if no credentials are
// present.
func (s *keyringStore) Delete() error {
	err := runWithTimeout(keyringTimeout, func() error {
		return keyring.Delete(keyringService, keyringAccount)
	})
	if err != nil && !errors.Is(err, keyring.ErrNotFound) {
		return fmt.Errorf("deleting from keyring: %w", err)
	}

	return nil
}

// Load reads and decodes the stored credentials, or returns ErrNotFound if
// none exist.
func (s *keyringStore) Load() (Credentials, error) {
	var raw string

	err := runWithTimeout(keyringTimeout, func() error {
		v, err := keyring.Get(keyringService, keyringAccount)
		if err != nil {
			return err
		}

		raw = v

		return nil
	})
	if err != nil {
		if errors.Is(err, keyring.ErrNotFound) {
			return Credentials{}, ErrNotFound
		}

		return Credentials{}, fmt.Errorf("reading from keyring: %w", err)
	}

	var creds Credentials
	if err := json.Unmarshal([]byte(raw), &creds); err != nil {
		return Credentials{}, fmt.Errorf("decoding credentials from keyring: %w", err)
	}

	return creds, nil
}

// Save serialises creds to JSON and writes them to the keyring.
func (s *keyringStore) Save(creds Credentials) error {
	body, err := json.Marshal(creds)
	if err != nil {
		return fmt.Errorf("encoding credentials: %w", err)
	}

	if err := runWithTimeout(keyringTimeout, func() error {
		return keyring.Set(keyringService, keyringAccount, string(body))
	}); err != nil {
		return fmt.Errorf("writing to keyring: %w", err)
	}

	return nil
}

// keyringHealthy reports whether the OS keyring backend appears to be
// reachable. A reachable backend may legitimately have no value at the
// probe key (returning ErrNotFound), so that case counts as healthy. Other
// errors (D-Bus unavailable, timeout, permission denied) indicate the
// backend should not be used.
func keyringHealthy() bool {
	err := runWithTimeout(keyringTimeout, func() error {
		_, err := keyring.Get(keyringHealthService, keyringHealthAccount)

		return err
	})

	return err == nil || errors.Is(err, keyring.ErrNotFound)
}

// runWithTimeout runs op in a goroutine, returning errKeyringTimeout if op
// does not complete within timeout.
//
// On timeout the goroutine outlives this call and exits when op finally
// returns; the buffered result channel guarantees it never blocks on send.
// Repeated calls against a hung backend can't accumulate stuck goroutines
// because keyringHealthy is consulted exactly once at credstore.New, and
// an unhealthy backend routes the rest of the process to the file store.
// zalando/go-keyring exposes no context-aware variant, so a cancellable
// alternative would require forking the dependency.
func runWithTimeout(timeout time.Duration, op func() error) error {
	ch := make(chan error, 1)

	go func() {
		ch <- op()
	}()

	select {
	case err := <-ch:
		return err
	case <-time.After(timeout):
		return errKeyringTimeout
	}
}
