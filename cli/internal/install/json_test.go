package install

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func readJSON(t *testing.T, path string) map[string]any {
	t.Helper()
	data, err := os.ReadFile(path)
	require.NoError(t, err)
	var m map[string]any
	require.NoError(t, json.Unmarshal(data, &m))
	return m
}

func TestUpsertCreatesNestedAndPreservesSiblings(t *testing.T) {
	p := filepath.Join(t.TempDir(), "mcp_config.json")
	require.NoError(t, os.WriteFile(p, []byte(`{"mcpServers":{"other":{"command":"x"}}}`), 0o644))

	c, err := upsertJSONEntry(
		p,
		[]string{"mcpServers", "cq"},
		map[string]any{"command": "/bin/cq", "args": []any{"mcp"}},
		false,
	)
	require.NoError(t, err)
	require.Equal(t, ActionCreated, c.Action)

	m := readJSON(t, p)
	servers := m["mcpServers"].(map[string]any)
	require.Contains(t, servers, "other")
	require.Equal(t, "/bin/cq", servers["cq"].(map[string]any)["command"])
}

func TestUpsertIdempotent(t *testing.T) {
	p := filepath.Join(t.TempDir(), "mcp_config.json")
	desired := map[string]any{"command": "/bin/cq", "args": []any{"mcp"}}
	_, err := upsertJSONEntry(p, []string{"mcpServers", "cq"}, desired, false)
	require.NoError(t, err)
	c, err := upsertJSONEntry(p, []string{"mcpServers", "cq"}, desired, false)
	require.NoError(t, err)
	require.Equal(t, ActionUnchanged, c.Action)
}

func TestRemoveEntryPrunesEmptyParent(t *testing.T) {
	p := filepath.Join(t.TempDir(), "mcp_config.json")
	_, err := upsertJSONEntry(p, []string{"mcpServers", "cq"}, map[string]any{"command": "/bin/cq"}, false)
	require.NoError(t, err)
	c, err := removeJSONEntry(p, []string{"mcpServers", "cq"}, false)
	require.NoError(t, err)
	require.Equal(t, ActionRemoved, c.Action)
	m := readJSON(t, p)
	require.NotContains(t, m, "mcpServers")
}

func TestUpsertRejectsNonObjectIntermediate(t *testing.T) {
	p := filepath.Join(t.TempDir(), "mcp_config.json")
	require.NoError(t, os.WriteFile(p, []byte(`{"mcpServers":"oops"}`), 0o644))
	_, err := upsertJSONEntry(p, []string{"mcpServers", "cq"}, map[string]any{"command": "/bin/cq"}, false)
	require.Error(t, err)
}

func TestUpsertRejectsNullConfig(t *testing.T) {
	p := filepath.Join(t.TempDir(), "mcp_config.json")
	require.NoError(t, os.WriteFile(p, []byte("null"), 0o644))
	_, err := upsertJSONEntry(p, []string{"mcpServers", "cq"}, map[string]any{"command": "/bin/cq"}, false)
	require.Error(t, err)
}

func TestJSONEntryRejectsEmptyPath(t *testing.T) {
	p := filepath.Join(t.TempDir(), "mcp_config.json")
	require.NoError(t, os.WriteFile(p, []byte("{}"), 0o644))
	_, err := upsertJSONEntry(p, nil, map[string]any{"command": "/bin/cq"}, false)
	require.Error(t, err)
	_, err = removeJSONEntry(p, nil, false)
	require.Error(t, err)
}

func TestJSONEntryRejectsBlankKey(t *testing.T) {
	p := filepath.Join(t.TempDir(), "mcp_config.json")
	require.NoError(t, os.WriteFile(p, []byte("{}"), 0o644))
	_, err := upsertJSONEntry(p, []string{"mcpServers", "  "}, map[string]any{"command": "/bin/cq"}, false)
	require.Error(t, err)
}
