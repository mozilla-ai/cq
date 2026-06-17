package install

import "path/filepath"

// SharedSkillsDir returns the cross-host skills commons under root.
//
// All non-Claude hosts read skills from this location, so the skill is
// written once per scope rather than copied per host.
func SharedSkillsDir(root string) string {
	return filepath.Join(root, ".agents", "skills")
}

// cursorTarget returns the Cursor configuration directory under home.
//
// Cursor reads config from <home>/.cursor on every platform.
func cursorTarget(home string) string {
	return filepath.Join(home, ".cursor")
}

// windsurfTarget returns the Windsurf configuration directory under home.
func windsurfTarget(home string) string {
	return filepath.Join(home, ".codeium", "windsurf")
}
