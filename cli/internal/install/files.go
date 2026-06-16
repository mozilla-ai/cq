package install

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// manifestName is the file recording installer-owned files in a directory.
const manifestName = ".cq-install-manifest.json"

// removeManagedFiles deletes the files recorded in dir's manifest, leaving any
// the user has modified in place and reporting SKIPPED when it does.
func removeManagedFiles(dir string, dryRun bool) (Change, error) {
	manifestPath := filepath.Join(dir, manifestName)
	m, err := loadManifest(manifestPath)
	if err != nil {
		return Change{}, err
	}
	if m == nil {
		return Change{Action: ActionUnchanged, Path: dir}, nil
	}
	skipped := false
	for _, e := range m.Files {
		target, joinErr := safeJoin(dir, e.Path)
		if joinErr != nil {
			return Change{}, joinErr
		}
		digest, hashErr := hashFile(target)
		if os.IsNotExist(hashErr) {
			continue
		}
		if hashErr != nil {
			return Change{}, hashErr
		}
		if digest != e.SHA256 {
			skipped = true
			continue
		}
		if !dryRun {
			if err := os.Remove(target); err != nil {
				return Change{}, fmt.Errorf("removing installed file: %w", err)
			}
		}
	}
	if skipped {
		return Change{Action: ActionSkipped, Path: dir, Detail: "user-modified files left in place"}, nil
	}
	if !dryRun {
		if err := os.Remove(manifestPath); err != nil && !os.IsNotExist(err) {
			return Change{}, fmt.Errorf("removing install manifest: %w", err)
		}
	}
	return Change{Action: ActionRemoved, Path: dir}, nil
}

// writeManagedFiles writes rel→content into dir, tracked by a manifest.
//
// Re-runs are idempotent: files whose content already matches are left
// UNCHANGED, and files written previously but absent from the new set are
// pruned.
// A file that differs from the desired content is overwritten only when it is
// our own previously-written file (e.g. a version bump); a file the user or
// another tool has created or edited is left untouched and reported SKIPPED.
//
// NOTE: the manifest is the source of truth for ownership; never overwrite or
// remove a file it does not record as ours.
func writeManagedFiles(dir string, files map[string]string, dryRun bool) (Change, error) {
	manifestPath := filepath.Join(dir, manifestName)
	previous, err := loadManifest(manifestPath)
	if err != nil {
		return Change{}, err
	}
	firstInstall := previous == nil

	prevHash := make(map[string]string, len(files))
	if previous != nil {
		for _, e := range previous.Files {
			prevHash[e.Path] = e.SHA256
		}
	}

	desired := make(map[string]bool, len(files))
	rels := make([]string, 0, len(files))
	for rel := range files {
		desired[rel] = true
		rels = append(rels, rel)
	}
	sort.Strings(rels)

	entries := make([]manifestEntry, 0, len(rels))
	changed := false
	skipped := false
	for _, rel := range rels {
		content := files[rel]
		sum := sha256.Sum256([]byte(content))
		digest := hex.EncodeToString(sum[:])

		target, joinErr := safeJoin(dir, rel)
		if joinErr != nil {
			return Change{}, joinErr
		}
		existing, readErr := os.ReadFile(target)
		if readErr != nil && !os.IsNotExist(readErr) {
			return Change{}, fmt.Errorf("reading existing file: %w", readErr)
		}
		if readErr == nil {
			cur := sha256.Sum256(existing)
			onDisk := hex.EncodeToString(cur[:])
			if onDisk == digest {
				if _, owned := prevHash[rel]; !owned {
					// A pre-existing file we never wrote, even if its content
					// matches: leave it unmanaged so uninstall never deletes it.
					skipped = true
					continue
				}
				entries = append(entries, manifestEntry{Path: rel, SHA256: digest})
				continue
			}
			if prev, owned := prevHash[rel]; !owned || onDisk != prev {
				// The user or another tool owns this file; do not overwrite it.
				skipped = true
				continue
			}
		}
		changed = true
		if !dryRun {
			if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
				return Change{}, fmt.Errorf("creating skill directory: %w", err)
			}
			if err := os.WriteFile(target, []byte(content), 0o644); err != nil {
				return Change{}, fmt.Errorf("writing skill file: %w", err)
			}
		}
		entries = append(entries, manifestEntry{Path: rel, SHA256: digest})
	}

	if previous != nil {
		for _, e := range previous.Files {
			if desired[e.Path] {
				continue
			}
			stale, joinErr := safeJoin(dir, e.Path)
			if joinErr != nil {
				return Change{}, joinErr
			}
			digest, hashErr := hashFile(stale)
			if os.IsNotExist(hashErr) {
				continue
			}
			if hashErr != nil {
				return Change{}, hashErr
			}
			if digest != e.SHA256 {
				// The user modified a now-stale file; leave it in place and
				// surface that a managed prune was skipped.
				skipped = true
				continue
			}
			changed = true
			if !dryRun {
				if err := os.Remove(stale); err != nil {
					return Change{}, fmt.Errorf("pruning stale file: %w", err)
				}
			}
		}
	}

	if !changed {
		if skipped {
			return Change{Action: ActionSkipped, Path: dir, Detail: "user-modified files left in place"}, nil
		}
		if !firstInstall {
			return Change{Action: ActionUnchanged, Path: dir}, nil
		}
	}
	if !dryRun {
		if err := writeManifest(manifestPath, entries); err != nil {
			return Change{}, err
		}
	}
	action := ActionUpdated
	if firstInstall {
		action = ActionCreated
	}
	return Change{Action: action, Path: dir}, nil
}

// safeJoin joins rel onto dir and rejects results that escape dir.
//
// NOTE: manifest paths are read from an on-disk file other local processes
// can write, so they must be treated as untrusted.
func safeJoin(dir, rel string) (string, error) {
	joined := filepath.Join(dir, rel)
	root := filepath.Clean(dir)
	if joined != root && !strings.HasPrefix(joined, root+string(os.PathSeparator)) {
		return "", fmt.Errorf("managed file path escapes its directory: %s", rel)
	}
	return joined, nil
}
