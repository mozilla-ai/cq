package cq

import "net/url"

// dropWindowsDriveSeparator drops the separator a host-less URL keeps in front
// of a Windows drive letter, so the drive letter is a volume name again.
//
// A host-less URL keeps the separator that introduces its path, so the
// documented sqlite:///C:/data/local.db form arrives as "/C:/data/local.db".
// On Windows that is a path rooted at the current drive's root rather than the
// C: drive, which no filesystem call can create.
//
// A UNC prefix is outside the rule and stays that way, because the character
// after the separator is another separator rather than a letter:
// sqlite:///\\host\share\local.db is not touched.
//
// NOTE: the rule holds on Windows only. On other platforms "/c:/data" is a
// legitimate absolute path whose leading separator carries meaning.
func dropWindowsDriveSeparator(path string) string {
	const minDriveLen = 3 // "/", the drive letter, and ":"

	if len(path) >= minDriveLen &&
		(path[0] == '/' || path[0] == '\\') &&
		isASCIILetter(path[1]) &&
		path[2] == ':' {
		return path[1:]
	}

	return path
}

// isASCIILetter reports whether c is an ASCII letter, the only character a
// Windows drive letter can be.
func isASCIILetter(c byte) bool {
	return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
}

// sqlitePathFromURL extracts the filesystem path from a parsed sqlite: URL.
// It accepts both the sqlite:///abs/path host-less form and the sqlite:path
// opaque form.
func sqlitePathFromURL(parsed *url.URL) string {
	if parsed.Opaque != "" {
		return parsed.Opaque
	}

	return storePathFromURLPath(parsed.Path)
}
