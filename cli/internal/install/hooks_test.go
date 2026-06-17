package install

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestUpsertHookEntrySeedsVersionAndIsIdempotent(t *testing.T) {
	p := filepath.Join(t.TempDir(), "hooks.json")

	c, err := upsertHookEntry(p, "sessionStart", "cq _hook --mode session-start", false)
	require.NoError(t, err)
	require.Equal(t, ActionCreated, c.Action)

	m := readJSON(t, p)
	require.EqualValues(t, 1, m["version"])
	hooks := m["hooks"].(map[string]any)
	entries := hooks["sessionStart"].([]any)
	require.Len(t, entries, 1)
	require.Equal(t, "cq _hook --mode session-start", entries[0].(map[string]any)["command"])

	c, err = upsertHookEntry(p, "sessionStart", "cq _hook --mode session-start", false)
	require.NoError(t, err)
	require.Equal(t, ActionUnchanged, c.Action)
}

func TestUpsertHookEntryPreservesForeignEntries(t *testing.T) {
	p := filepath.Join(t.TempDir(), "hooks.json")
	require.NoError(t, os.WriteFile(p, []byte(
		`{"version":1,"hooks":{"sessionStart":[{"command":"other-tool"}]}}`), 0o644))

	c, err := upsertHookEntry(p, "sessionStart", "cq _hook --mode session-start", false)
	require.NoError(t, err)
	require.Equal(t, ActionUpdated, c.Action)

	hooks := readJSON(t, p)["hooks"].(map[string]any)
	entries := hooks["sessionStart"].([]any)
	require.Len(t, entries, 2)
}

func TestRemoveHookEntryPrunesEmptyEvent(t *testing.T) {
	p := filepath.Join(t.TempDir(), "hooks.json")
	_, err := upsertHookEntry(p, "stop", "cq _hook --mode stop", false)
	require.NoError(t, err)

	c, err := removeHookEntry(p, "stop", "cq _hook --mode stop", false)
	require.NoError(t, err)
	require.Equal(t, ActionRemoved, c.Action)

	hooks := readJSON(t, p)["hooks"].(map[string]any)
	require.NotContains(t, hooks, "stop")
}

func TestRemoveHookEntryLeavesForeignEntries(t *testing.T) {
	p := filepath.Join(t.TempDir(), "hooks.json")
	require.NoError(t, os.WriteFile(p, []byte(
		`{"version":1,"hooks":{"stop":[{"command":"other-tool"},{"command":"cq _hook --mode stop"}]}}`), 0o644))

	c, err := removeHookEntry(p, "stop", "cq _hook --mode stop", false)
	require.NoError(t, err)
	require.Equal(t, ActionRemoved, c.Action)

	entries := readJSON(t, p)["hooks"].(map[string]any)["stop"].([]any)
	require.Len(t, entries, 1)
	require.Equal(t, "other-tool", entries[0].(map[string]any)["command"])
}

func TestRemoveHookEntryAbsentFileIsUnchanged(t *testing.T) {
	p := filepath.Join(t.TempDir(), "hooks.json")
	c, err := removeHookEntry(p, "stop", "cq _hook --mode stop", false)
	require.NoError(t, err)
	require.Equal(t, ActionUnchanged, c.Action)
}

func TestUpsertHookEntryRejectsMalformedHooks(t *testing.T) {
	p := filepath.Join(t.TempDir(), "hooks.json")
	require.NoError(t, os.WriteFile(p, []byte(`{"hooks":"oops"}`), 0o644))
	_, err := upsertHookEntry(p, "stop", "cq _hook --mode stop", false)
	require.Error(t, err)

	require.NoError(t, os.WriteFile(p, []byte(`{"version":1,"hooks":{"stop":"oops"}}`), 0o644))
	_, err = upsertHookEntry(p, "stop", "cq _hook --mode stop", false)
	require.Error(t, err)
}

func TestRemoveHookEntryMalformedHooksSkips(t *testing.T) {
	p := filepath.Join(t.TempDir(), "hooks.json")
	require.NoError(t, os.WriteFile(p, []byte(`{"hooks":"oops"}`), 0o644))
	c, err := removeHookEntry(p, "stop", "cq _hook --mode stop", false)
	require.NoError(t, err)
	require.Equal(t, ActionSkipped, c.Action)
}

func TestHookEntryHandlesNonStringCommand(t *testing.T) {
	p := filepath.Join(t.TempDir(), "hooks.json")
	require.NoError(t, os.WriteFile(p, []byte(
		`{"version":1,"hooks":{"stop":[{"command":["not","a","string"]}]}}`), 0o644))

	// Upsert treats the non-string entry as foreign and appends ours.
	c, err := upsertHookEntry(p, "stop", "cq _hook --mode stop", false)
	require.NoError(t, err)
	require.Equal(t, ActionUpdated, c.Action)

	// Remove skips the non-string entry and removes only ours.
	c, err = removeHookEntry(p, "stop", "cq _hook --mode stop", false)
	require.NoError(t, err)
	require.Equal(t, ActionRemoved, c.Action)

	// The non-string entry is still there.
	hooks := readJSON(t, p)["hooks"].(map[string]any)
	entries := hooks["stop"].([]any)
	require.Len(t, entries, 1)
}

func TestUpsertHookEntryRejectsNullConfig(t *testing.T) {
	p := filepath.Join(t.TempDir(), "hooks.json")
	require.NoError(t, os.WriteFile(p, []byte("null"), 0o644))
	_, err := upsertHookEntry(p, "stop", "cq _hook --mode stop", false)
	require.Error(t, err)
}
