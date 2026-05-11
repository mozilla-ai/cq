package auth

// browserCommand returns macOS's default URL handler.
func browserCommand(url string) (name string, args []string) {
	return "open", []string{url}
}
