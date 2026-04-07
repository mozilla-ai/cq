// Package version provides build-time version information.
package version

import "fmt"

// These variables should not be moved or renamed without updating the
// Makefile LDFLAGS, which inject values at build time.
var (
	version = "dev"
	commit  = "unknown"
	date    = "unknown"
)

// Version returns the raw version string.
func Version() string {
	return version
}

// String returns the full version string including commit and build date.
func String() string {
	return fmt.Sprintf("cq-sdk v%s (%s), built %s", version, commit, date)
}
