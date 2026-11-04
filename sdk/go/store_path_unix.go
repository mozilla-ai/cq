//go:build !windows

package cq

// storePathFromURLPath turns the path of a host-less sqlite: URL into a
// filesystem path. The separator that introduces the path carries meaning on
// this platform, so the path is used as it is.
func storePathFromURLPath(path string) string {
	return path
}
