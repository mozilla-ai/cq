package cmd

import (
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
)

// testSetup configures env vars and flag state for an isolated test client.
func testSetup(t *testing.T) {
	t.Helper()

	dbPath := filepath.Join(t.TempDir(), "test.db")
	t.Setenv(envVarDBPath, dbPath)
	t.Setenv(envVarAddr, "")
	t.Setenv(envVarAPIKey, "")

	// Set package-level flag vars that newCLIClient reads.
	setFlag(t, &flagDBPath, dbPath)
	setFlag(t, &flagAddr, "")
	setFlag(t, &flagAPIKey, "")
}

// setFlag sets a package-level flag variable and restores it after the test.
func setFlag(t *testing.T, target *string, value string) {
	t.Helper()

	prev := *target
	*target = value

	t.Cleanup(func() { *target = prev })
}

// withFakeRemote starts a fake remote API on a test server, points the
// CLI's --addr flag at it, and registers cleanup. Callers that need an
// API key on the wire should setFlag(&flagAPIKey, ...) separately.
func withFakeRemote(t *testing.T, handler http.Handler) {
	t.Helper()

	srv := httptest.NewServer(withDiscoveryNotFound(handler))
	t.Cleanup(srv.Close)
	t.Setenv("XDG_CACHE_HOME", t.TempDir())
	setFlag(t, &flagAddr, srv.URL)
}

// withDiscoveryNotFound wraps handler so the discovery probe sees a 404
// at the well-known path and the SDK falls back to addr + /api/v1.
// Other paths flow through to handler unchanged.
func withDiscoveryNotFound(handler http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/.well-known/cq-node.json" {
			http.NotFound(w, r)
			return
		}
		handler.ServeHTTP(w, r)
	})
}
