package install

import (
	"fmt"
	"os"
	"path/filepath"
)

// binaryOverrideEnv forces the binary path written into host config.
//
// NOTE: set it to an absolute path to override the auto-resolved binary
// location, for example when a wrapper sits in front of the real binary.
const binaryOverrideEnv = "CQ_INSTALL_BINARY"

// BinaryPath returns the absolute path to write into a host's MCP config so
// the host can spawn `cq mcp` regardless of its PATH at launch time.
//
// NOTE: the path is intentionally NOT symlink-resolved. On Homebrew the
// resolved path points into a versioned Cellar directory that moves on
// upgrade; the stable invocation path survives upgrades. Verify on
// Homebrew and Scoop when changing this.
func BinaryPath() (string, error) {
	if override := os.Getenv(binaryOverrideEnv); override != "" {
		if !filepath.IsAbs(override) {
			return "", fmt.Errorf("%s must be an absolute path: %s", binaryOverrideEnv, override)
		}
		return override, nil
	}
	return os.Executable()
}
