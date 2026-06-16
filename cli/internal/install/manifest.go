package install

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// manifestEntry records one installed file and its content hash.
type manifestEntry struct {
	// Path is the file's path relative to the install directory.
	Path string `json:"path"`

	// SHA256 is the hex sha256 of the file's content at install time.
	SHA256 string `json:"sha256"`
}

// manifest is the set of files an install owns within a directory.
type manifest struct {
	// Files lists each owned file with the hash written for it.
	Files []manifestEntry `json:"files"`
}

// hashFile returns the lowercase hex sha256 of the file at path.
func hashFile(path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("reading file to hash: %w", err)
	}
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:]), nil
}

// loadManifest reads the manifest at path, returning nil when it is absent.
func loadManifest(path string) (*manifest, error) {
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("reading install manifest: %w", err)
	}
	var m manifest
	if err := json.Unmarshal(data, &m); err != nil {
		return nil, fmt.Errorf("parsing install manifest: %w", err)
	}
	return &m, nil
}

// writeManifest writes entries to the manifest at path with a trailing newline.
func writeManifest(path string, entries []manifestEntry) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return fmt.Errorf("creating manifest directory: %w", err)
	}
	data, err := json.MarshalIndent(manifest{Files: entries}, "", "  ")
	if err != nil {
		return fmt.Errorf("encoding install manifest: %w", err)
	}
	if err := os.WriteFile(path, append(data, '\n'), 0o644); err != nil {
		return fmt.Errorf("writing install manifest: %w", err)
	}
	return nil
}
