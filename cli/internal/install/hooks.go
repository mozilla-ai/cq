package install

import "fmt"

// hookCommandField is the key Cursor reads for a hook's shell command.
const hookCommandField = "command"

// eventEntries returns hooks[event] as a slice, treating an absent key as empty
// and rejecting a non-array value.
func eventEntries(hooks map[string]any, event string) ([]any, error) {
	raw, present := hooks[event]
	if !present || raw == nil {
		return nil, nil
	}
	entries, ok := raw.([]any)
	if !ok {
		return nil, fmt.Errorf("hook entries for %q are not a list", event)
	}
	return entries, nil
}

// hooksObject returns root["hooks"] as an object, creating it when absent and
// rejecting a non-object value.
func hooksObject(root map[string]any) (map[string]any, error) {
	raw, present := root["hooks"]
	if !present || raw == nil {
		hooks := map[string]any{}
		root["hooks"] = hooks
		return hooks, nil
	}
	hooks, ok := raw.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("hooks configuration is not an object")
	}
	return hooks, nil
}

// removeHookEntry deletes the entry whose command matches under hooks.<event>,
// pruning the event key when it becomes empty.
//
// Returns UNCHANGED when the file or entry is absent, SKIPPED when the document
// is malformed (left untouched rather than rewritten).
func removeHookEntry(file, event, command string, dryRun bool) (Change, error) {
	root, err := loadJSONObject(file)
	if err != nil {
		return Change{}, err
	}
	rawHooks, present := root["hooks"]
	if !present {
		return Change{Action: ActionUnchanged, Path: file}, nil
	}
	hooks, ok := rawHooks.(map[string]any)
	if !ok {
		return Change{Action: ActionSkipped, Path: file, Detail: "malformed hooks document; left in place"}, nil
	}
	rawEntries, present := hooks[event]
	if !present {
		return Change{Action: ActionUnchanged, Path: file}, nil
	}
	entries, ok := rawEntries.([]any)
	if !ok {
		return Change{Action: ActionSkipped, Path: file, Detail: "malformed hooks document; left in place"}, nil
	}
	kept := make([]any, 0, len(entries))
	for _, e := range entries {
		if obj, ok := e.(map[string]any); ok {
			if cmd, ok := obj[hookCommandField].(string); ok && cmd == command {
				continue
			}
		}
		kept = append(kept, e)
	}
	if len(kept) == len(entries) {
		return Change{Action: ActionUnchanged, Path: file}, nil
	}
	if len(kept) == 0 {
		delete(hooks, event)
	} else {
		hooks[event] = kept
	}
	if !dryRun {
		if err := writeJSONObject(file, root); err != nil {
			return Change{}, err
		}
	}
	return Change{Action: ActionRemoved, Path: file, Detail: event}, nil
}

// upsertHookEntry adds or updates the {command} entry under hooks.<event> in a
// Cursor-style hooks file, seeding the required "version": 1 and preserving any
// foreign entries and sibling keys.
//
// Returns CREATED when the command was absent, UNCHANGED when it already
// matched. An invalid hooks document is rejected with an error rather than
// being silently overwritten.
func upsertHookEntry(file, event, command string, dryRun bool) (Change, error) {
	root, err := loadJSONObject(file)
	if err != nil {
		return Change{}, err
	}
	if _, ok := root["version"]; !ok {
		root["version"] = 1
	}
	hooks, err := hooksObject(root)
	if err != nil {
		return Change{}, err
	}
	entries, err := eventEntries(hooks, event)
	if err != nil {
		return Change{}, err
	}
	for _, e := range entries {
		if obj, ok := e.(map[string]any); ok {
			if cmd, ok := obj[hookCommandField].(string); ok && cmd == command {
				return Change{Action: ActionUnchanged, Path: file}, nil
			}
		}
	}
	hooks[event] = append(entries, map[string]any{hookCommandField: command})
	if !dryRun {
		if err := writeJSONObject(file, root); err != nil {
			return Change{}, err
		}
	}
	action := ActionUpdated
	if len(entries) == 0 {
		action = ActionCreated
	}
	return Change{Action: action, Path: file, Detail: event}, nil
}
