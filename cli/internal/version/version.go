// Package version provides build-time version information for the CLI.
package version

import "fmt"

// Build-time variables injected via ldflags; defaults are used for local development builds.
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
	return fmt.Sprintf("cq v%s (%s), built %s", version, commit, date)
}
