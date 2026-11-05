//go:build windows

package cq

// storePathFromURLPath turns the path of a host-less sqlite: URL into a
// filesystem path on Windows, where the separator in front of a drive letter
// has to go.
func storePathFromURLPath(path string) string {
	return dropWindowsDriveSeparator(path)
}
