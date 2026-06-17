//go:build windows

package install

// shellJoin quotes args for the host shell a coding-agent will use to run a hook command.
func shellJoin(args ...string) string {
	return windowsJoin(args)
}
