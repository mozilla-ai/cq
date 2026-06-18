package install

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strings"

	"github.com/BurntSushi/toml"
)

// upsertTOMLSection sets the values at a dotted key path in a TOML file,
// creating intermediate tables as needed and preserving sibling keys.
//
// Returns CREATED when the section was absent, UPDATED when a value changed,
// UNCHANGED when the section already matched.
// Returns an error when an intermediate or leaf key exists as a non-table value
// (the installer must not silently overwrite user-authored config).
func upsertTOMLSection(file string, section string, desired map[string]any, dryRun bool) (Change, error) {
	if err := validateTOMLSection(section); err != nil {
		return Change{}, err
	}

	root, err := loadTOML(file)
	if err != nil {
		return Change{}, err
	}

	keys := strings.Split(section, ".")
	parent := root
	for _, key := range keys[:len(keys)-1] {
		raw, present := parent[key]
		if !present {
			child := map[string]any{}
			parent[key] = child
			parent = child
			continue
		}
		child, ok := raw.(map[string]any)
		if !ok {
			return Change{}, fmt.Errorf("config key %q is not a table", key)
		}
		parent = child
	}

	leaf := keys[len(keys)-1]
	raw, present := parent[leaf]
	if present {
		existing, ok := raw.(map[string]any)
		if !ok {
			return Change{}, fmt.Errorf("config key %q is not a table", leaf)
		}
		if reflect.DeepEqual(existing, desired) {
			return Change{Action: ActionUnchanged, Path: file}, nil
		}
	}

	parent[leaf] = desired
	if dryRun {
		return Change{Action: upsertAction(present), Path: file}, nil
	}
	if err := writeTOML(file, root); err != nil {
		return Change{}, err
	}
	return Change{Action: upsertAction(present), Path: file}, nil
}

// removeTOMLSection deletes the entry at a dotted key path in a TOML file,
// pruning empty parent tables.
//
// Returns UNCHANGED when the file or section is absent.
func removeTOMLSection(file string, section string, dryRun bool) (Change, error) {
	if err := validateTOMLSection(section); err != nil {
		return Change{}, err
	}

	data, err := os.ReadFile(file)
	if os.IsNotExist(err) {
		return Change{Action: ActionUnchanged, Path: file}, nil
	}
	if err != nil {
		return Change{}, fmt.Errorf("reading config file: %w", err)
	}

	root := map[string]any{}
	if err := toml.Unmarshal(data, &root); err != nil {
		return Change{}, fmt.Errorf("parsing config file: %w", err)
	}

	keys := strings.Split(section, ".")
	tables := make([]map[string]any, 0, len(keys))
	cursor := root
	for _, key := range keys[:len(keys)-1] {
		child, ok := cursor[key].(map[string]any)
		if !ok {
			return Change{Action: ActionUnchanged, Path: file}, nil
		}
		tables = append(tables, cursor)
		cursor = child
	}

	leaf := keys[len(keys)-1]
	if _, ok := cursor[leaf]; !ok {
		return Change{Action: ActionUnchanged, Path: file}, nil
	}

	delete(cursor, leaf)

	for i := len(tables) - 1; i >= 0; i-- {
		key := keys[i]
		if child, ok := tables[i][key].(map[string]any); ok && len(child) == 0 {
			delete(tables[i], key)
		} else {
			break
		}
	}

	if dryRun {
		return Change{Action: ActionRemoved, Path: file}, nil
	}
	if err := writeTOML(file, root); err != nil {
		return Change{}, err
	}
	return Change{Action: ActionRemoved, Path: file}, nil
}

// loadTOML reads and parses a TOML file, returning an empty map when absent.
func loadTOML(file string) (map[string]any, error) {
	data, err := os.ReadFile(file)
	if os.IsNotExist(err) {
		return map[string]any{}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("reading config file: %w", err)
	}
	root := map[string]any{}
	if err := toml.Unmarshal(data, &root); err != nil {
		return nil, fmt.Errorf("parsing config file: %w", err)
	}
	return root, nil
}

// upsertAction returns UPDATED when the key was present, CREATED when absent.
func upsertAction(present bool) Action {
	if present {
		return ActionUpdated
	}
	return ActionCreated
}

// validateTOMLSection rejects empty or blank-segment section paths.
func validateTOMLSection(section string) error {
	if strings.TrimSpace(section) == "" {
		return fmt.Errorf("config section path must not be empty")
	}
	for _, seg := range strings.Split(section, ".") {
		if strings.TrimSpace(seg) == "" {
			return fmt.Errorf("config section path contains an empty segment: %q", section)
		}
	}
	return nil
}

// writeTOML encodes root to file as TOML, creating parent directories as
// needed.
func writeTOML(file string, root map[string]any) error {
	var buf bytes.Buffer
	enc := toml.NewEncoder(&buf)
	if err := enc.Encode(root); err != nil {
		return fmt.Errorf("encoding config file: %w", err)
	}
	if err := os.MkdirAll(filepath.Dir(file), 0o755); err != nil {
		return fmt.Errorf("creating config directory: %w", err)
	}
	if err := os.WriteFile(file, buf.Bytes(), 0o644); err != nil {
		return fmt.Errorf("writing config file: %w", err)
	}
	return nil
}
