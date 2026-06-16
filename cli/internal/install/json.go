package install

import (
	"encoding/json"
	"fmt"
	"maps"
	"os"
	"path/filepath"
	"reflect"
	"strings"
)

// removeJSONEntry deletes the entry at the given key path, pruning parents that
// become empty.
//
// Returns UNCHANGED when the entry is absent.
func removeJSONEntry(file string, keys []string, dryRun bool) (Change, error) {
	if err := validateKeys(keys); err != nil {
		return Change{}, err
	}
	if _, err := os.Stat(file); os.IsNotExist(err) {
		return Change{Action: ActionUnchanged, Path: file}, nil
	}
	root, err := loadJSONObject(file)
	if err != nil {
		return Change{}, err
	}
	parents := make([]map[string]any, 0, len(keys))
	cursor := root
	for _, key := range keys[:len(keys)-1] {
		child, ok := cursor[key].(map[string]any)
		if !ok {
			return Change{Action: ActionUnchanged, Path: file}, nil
		}
		parents = append(parents, cursor)
		cursor = child
	}
	leaf := keys[len(keys)-1]
	if _, ok := cursor[leaf]; !ok {
		return Change{Action: ActionUnchanged, Path: file}, nil
	}
	delete(cursor, leaf)
	// Walk back up: parents[i] is the object at depth i and keys[i] is the key
	// within it that led down the path; drop any parent left empty.
	for i := len(parents) - 1; i >= 0; i-- {
		key := keys[i]
		if child, ok := parents[i][key].(map[string]any); ok && len(child) == 0 {
			delete(parents[i], key)
		} else {
			break
		}
	}
	if !dryRun {
		if err := writeJSONObject(file, root); err != nil {
			return Change{}, err
		}
	}
	return Change{Action: ActionRemoved, Path: file}, nil
}

// upsertJSONEntry merges desired into file at the given key path, preserving
// sibling keys and creating intermediate objects.
//
// Returns CREATED when the leaf was absent, UPDATED when a managed field
// changed, UNCHANGED otherwise.
func upsertJSONEntry(file string, keys []string, desired map[string]any, dryRun bool) (Change, error) {
	if err := validateKeys(keys); err != nil {
		return Change{}, err
	}
	root, err := loadJSONObject(file)
	if err != nil {
		return Change{}, err
	}
	cursor := root
	for _, key := range keys[:len(keys)-1] {
		existing, present := cursor[key]
		if !present || existing == nil {
			child := map[string]any{}
			cursor[key] = child
			cursor = child
			continue
		}
		child, ok := existing.(map[string]any)
		if !ok {
			return Change{}, fmt.Errorf("config entry %q is not an object", key)
		}
		cursor = child
	}
	leaf := keys[len(keys)-1]
	existing, ok := cursor[leaf].(map[string]any)
	action := ActionUpdated
	if !ok {
		// Clone so the stored entry is not aliased to the caller's map.
		cursor[leaf] = maps.Clone(desired)
		action = ActionCreated
	} else {
		changed := false
		for k, v := range desired {
			if !reflect.DeepEqual(existing[k], v) {
				existing[k] = v
				changed = true
			}
		}
		if !changed {
			return Change{Action: ActionUnchanged, Path: file}, nil
		}
	}
	if !dryRun {
		if err := writeJSONObject(file, root); err != nil {
			return Change{}, err
		}
	}
	return Change{Action: action, Path: file}, nil
}

// loadJSONObject reads the file at path into a map, treating a missing file as empty.
func loadJSONObject(path string) (map[string]any, error) {
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return map[string]any{}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("reading config file: %w", err)
	}
	if len(data) == 0 {
		return map[string]any{}, nil
	}
	var m map[string]any
	if err := json.Unmarshal(data, &m); err != nil {
		return nil, fmt.Errorf("config file is not a JSON object: %w", err)
	}
	if m == nil {
		// A file containing literal `null` decodes to a nil map; treat it as
		// malformed rather than letting callers assign into a nil map.
		return nil, fmt.Errorf("config file is not a JSON object")
	}
	return m, nil
}

// validateKeys rejects an empty key path or any blank key, which would otherwise
// index out of range or create a meaningless empty-string object key.
func validateKeys(keys []string) error {
	if len(keys) == 0 {
		return fmt.Errorf("config key path must contain at least one key")
	}
	for _, k := range keys {
		if strings.TrimSpace(k) == "" {
			return fmt.Errorf("config key path must not contain a blank key")
		}
	}
	return nil
}

// writeJSONObject writes m to the file at path with two-space indent and a trailing newline.
//
// NOTE: Go marshals object keys in sorted order. Phase 1 accepts this; later
// phases that touch large user-authored config preserve key order.
func writeJSONObject(path string, m map[string]any) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return fmt.Errorf("creating config directory: %w", err)
	}
	data, err := json.MarshalIndent(m, "", "  ")
	if err != nil {
		return fmt.Errorf("encoding config file: %w", err)
	}
	if err := os.WriteFile(path, append(data, '\n'), 0o644); err != nil {
		return fmt.Errorf("writing config file: %w", err)
	}
	return nil
}
