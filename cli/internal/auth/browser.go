package auth

import (
	"fmt"
	"os/exec"
)

// openBrowser launches the user's default browser pointing at url.
// The platform-specific launcher and arguments come from
// browserCommand, which is implemented in a per-OS file via build
// tags so this file does not need to branch on runtime.GOOS.
//
// This is a best-effort UX affordance: if the launcher fails or no
// graphical environment is available, the caller should still print
// the URL so the user can paste it manually.
func openBrowser(url string) error {
	name, args := browserCommand(url)

	cmd := exec.Command(name, args...)
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("opening browser via '%s': %w", name, err)
	}

	// Don't Wait: the launcher (xdg-open / open / rundll32) typically
	// returns immediately after handing off to the browser process.
	// Releasing lets the child run independently of this CLI.
	_ = cmd.Process.Release()

	return nil
}
