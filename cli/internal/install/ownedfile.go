package install

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
)

// removeOwnedFile deletes path only when its content still hashes to
// wantHash, the value written at install time.
//
// Returns SKIPPED when the file has been modified since install (left in
// place), UNCHANGED when it is already absent.
func removeOwnedFile(path, wantHash string, dryRun bool) (Change, error) {
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return Change{Action: ActionUnchanged, Path: path}, nil
	}
	if err != nil {
		return Change{}, fmt.Errorf("reading target file: %w", err)
	}
	if sha256Hex(string(data)) != wantHash {
		return Change{Action: ActionSkipped, Path: path, Detail: "modified since install; left in place"}, nil
	}
	if !dryRun {
		if err := os.Remove(path); err != nil {
			return Change{}, fmt.Errorf("removing config file: %w", err)
		}
	}
	return Change{Action: ActionRemoved, Path: path}, nil
}

// sha256Hex returns the lowercase hex sha256 of s.
func sha256Hex(s string) string {
	sum := sha256.Sum256([]byte(s))
	return hex.EncodeToString(sum[:])
}

// writeIfMissing creates path with content when it does not yet exist.
//
// NOTE: an existing file is never overwritten, so a user's edits to a
// previously-installed file always survive a re-install.
func writeIfMissing(path, content string, dryRun bool) (Change, error) {
	if _, err := os.Stat(path); err == nil {
		return Change{Action: ActionUnchanged, Path: path}, nil
	} else if !os.IsNotExist(err) {
		return Change{}, fmt.Errorf("checking target file: %w", err)
	}
	if !dryRun {
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			return Change{}, fmt.Errorf("creating config directory: %w", err)
		}
		if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
			return Change{}, fmt.Errorf("writing config file: %w", err)
		}
	}
	return Change{Action: ActionCreated, Path: path}, nil
}
