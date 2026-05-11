package auth

// browserCommand returns Windows's default URL handler. rundll32 with
// FileProtocolHandler delegates URL opening to whichever browser is
// registered as the default in the user's settings.
func browserCommand(url string) (name string, args []string) {
	return "rundll32", []string{"url.dll,FileProtocolHandler", url}
}
