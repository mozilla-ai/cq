package cmd

import (
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
