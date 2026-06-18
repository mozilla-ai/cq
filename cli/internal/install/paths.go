package install

import (
	"os"
	"path/filepath"
	"runtime"
)

// opencodeConfigDirEnv overrides the default OpenCode config directory.
//
// NOTE: OpenCode does not honor XDG_CONFIG_HOME; it always reads from
// ~/.config/opencode unless this env var is set.
const opencodeConfigDirEnv = "OPENCODE_CONFIG_DIR"

// SharedSkillsDir returns the cross-host skills commons under root.
//
// All non-Claude hosts read skills from this location, so the skill is
// written once per scope rather than copied per host.
func SharedSkillsDir(root string) string {
	return filepath.Join(root, ".agents", "skills")
}

// copilotTarget returns the VSCode user configuration directory.
//
// VSCode stores user-level config under a platform-specific directory:
//   - macOS:   ~/Library/Application Support/Code/User
//   - Linux:   ~/.config/Code/User
//   - Windows: ~/AppData/Roaming/Code/User
//
// NOTE: targets the default VSCode profile only.
// Custom profiles store config in a profiles/<id>/ subdirectory; VSCode
// Insiders uses "Code - Insiders" instead of "Code".
func copilotTarget(home string) string {
	switch runtime.GOOS {
	case "darwin":
		return filepath.Join(home, "Library", "Application Support", "Code", "User")
	case "windows":
		return filepath.Join(home, "AppData", "Roaming", "Code", "User")
	default:
		return filepath.Join(home, ".config", "Code", "User")
	}
}

// cursorTarget returns the Cursor configuration directory under home.
//
// Cursor reads config from <home>/.cursor on every platform.
func cursorTarget(home string) string {
	return filepath.Join(home, ".cursor")
}

// opencodeTarget returns the OpenCode configuration directory.
//
// Honors OPENCODE_CONFIG_DIR the same way OpenCode itself does: if set, the
// env var wins; otherwise fall back to the default location under home.
func opencodeTarget(home string) string {
	if override := os.Getenv(opencodeConfigDirEnv); override != "" {
		return override
	}
	return filepath.Join(home, ".config", "opencode")
}

// piTarget returns the Pi global configuration directory under home.
//
// NOTE: Pi's global path has an extra "agent" segment (~/.pi/agent) that the
// per-project path (.pi/) does not.
func piTarget(home string) string {
	return filepath.Join(home, ".pi", "agent")
}

// windsurfTarget returns the Windsurf configuration directory under home.
func windsurfTarget(home string) string {
	return filepath.Join(home, ".codeium", "windsurf")
}
