package install

import "strings"

// posixJoin quotes each arg for a POSIX shell, single-quoting any arg with
// special characters and escaping embedded single quotes as: end-quote, backslash, single-quote, open-quote.
func posixJoin(args []string) string {
	quoted := make([]string, len(args))
	for i, arg := range args {
		if posixSafe(arg) {
			quoted[i] = arg
			continue
		}
		quoted[i] = "'" + strings.ReplaceAll(arg, "'", `'\''`) + "'"
	}
	return strings.Join(quoted, " ")
}

// posixSafe reports whether arg needs no quoting in a POSIX shell.
func posixSafe(arg string) bool {
	if arg == "" {
		return false
	}
	for _, r := range arg {
		switch {
		case r >= 'a' && r <= 'z', r >= 'A' && r <= 'Z', r >= '0' && r <= '9':
		case r == '-', r == '_', r == '.', r == '/', r == ':', r == '=', r == ',':
		default:
			return false
		}
	}
	return true
}

// quoteWindows quotes a single argument for the Windows command interpreter.
func quoteWindows(arg string) string {
	if arg != "" && !strings.ContainsAny(arg, " \t\n\v\"") {
		return arg
	}
	var b strings.Builder
	b.WriteByte('"')
	backslashes := 0
	for _, r := range arg {
		switch r {
		case '\\':
			backslashes++
		case '"':
			b.WriteString(strings.Repeat(`\`, backslashes*2+1))
			b.WriteByte('"')
			backslashes = 0
		default:
			b.WriteString(strings.Repeat(`\`, backslashes))
			b.WriteRune(r)
			backslashes = 0
		}
	}
	b.WriteString(strings.Repeat(`\`, backslashes*2))
	b.WriteByte('"')
	return b.String()
}

// windowsJoin quotes each arg following the CommandLineToArgvW rules used by the
// Windows command interpreter: double-quote any arg containing a space or quote,
// escaping embedded quotes and runs of backslashes that precede a quote.
func windowsJoin(args []string) string {
	quoted := make([]string, len(args))
	for i, arg := range args {
		quoted[i] = quoteWindows(arg)
	}
	return strings.Join(quoted, " ")
}
