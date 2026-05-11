//go:build !darwin && !windows

package auth

// browserCommand returns the freedesktop URL handler used on Linux and
// the BSDs. Every freedesktop-compliant desktop environment ships it.
func browserCommand(url string) (name string, args []string) {
	return "xdg-open", []string{url}
}
