package install

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestUpsertTOMLSectionCreatesFile(t *testing.T) {
	p := filepath.Join(t.TempDir(), "config.toml")
	c, err := upsertTOMLSection(p, "mcp_servers.cq", map[string]any{
		"command": "/bin/cq",
		"args":    []any{"mcp"},
	}, false)
	require.NoError(t, err)
	require.Equal(t, ActionCreated, c.Action)

	got, err := os.ReadFile(p)
	require.NoError(t, err)
	require.Contains(t, string(got), "[mcp_servers.cq]")
	require.Contains(t, string(got), `command = "/bin/cq"`)
	require.Contains(t, string(got), `"mcp"`)
}

func TestUpsertTOMLSectionIsIdempotent(t *testing.T) {
	p := filepath.Join(t.TempDir(), "config.toml")
	entry := map[string]any{"command": "/bin/cq", "args": []any{"mcp"}}
	_, err := upsertTOMLSection(p, "mcp_servers.cq", entry, false)
	require.NoError(t, err)
	c, err := upsertTOMLSection(p, "mcp_servers.cq", entry, false)
	require.NoError(t, err)
	require.Equal(t, ActionUnchanged, c.Action)
}

func TestUpsertTOMLSectionPreservesSiblings(t *testing.T) {
	p := filepath.Join(t.TempDir(), "config.toml")
	require.NoError(t, os.WriteFile(p, []byte("[mcp_servers.other]\ncommand = \"other\"\n"), 0o644))
	c, err := upsertTOMLSection(p, "mcp_servers.cq", map[string]any{
		"command": "/bin/cq",
		"args":    []any{"mcp"},
	}, false)
	require.NoError(t, err)
	require.Equal(t, ActionCreated, c.Action)

	got, err := os.ReadFile(p)
	require.NoError(t, err)
	require.Contains(t, string(got), "[mcp_servers.other]")
	require.Contains(t, string(got), "[mcp_servers.cq]")
}

func TestUpsertTOMLSectionUpdatesChanged(t *testing.T) {
	p := filepath.Join(t.TempDir(), "config.toml")
	require.NoError(t, os.WriteFile(p, []byte("[mcp_servers.cq]\ncommand = \"/old/cq\"\n"), 0o644))
	c, err := upsertTOMLSection(p, "mcp_servers.cq", map[string]any{
		"command": "/new/cq",
		"args":    []any{"mcp"},
	}, false)
	require.NoError(t, err)
	require.Equal(t, ActionUpdated, c.Action)

	got, err := os.ReadFile(p)
	require.NoError(t, err)
	require.Contains(t, string(got), `command = "/new/cq"`)
}

func TestUpsertTOMLSectionDryRunWritesNothing(t *testing.T) {
	p := filepath.Join(t.TempDir(), "config.toml")
	c, err := upsertTOMLSection(p, "mcp_servers.cq", map[string]any{
		"command": "/bin/cq",
	}, true)
	require.NoError(t, err)
	require.Equal(t, ActionCreated, c.Action)
	_, statErr := os.Stat(p)
	require.True(t, os.IsNotExist(statErr))
}

func TestRemoveTOMLSectionDeletesEntry(t *testing.T) {
	p := filepath.Join(t.TempDir(), "config.toml")
	require.NoError(t, os.WriteFile(p, []byte("[mcp_servers.cq]\ncommand = \"/bin/cq\"\n"), 0o644))
	c, err := removeTOMLSection(p, "mcp_servers.cq", false)
	require.NoError(t, err)
	require.Equal(t, ActionRemoved, c.Action)

	got, err := os.ReadFile(p)
	require.NoError(t, err)
	require.NotContains(t, string(got), "mcp_servers")
}

func TestRemoveTOMLSectionPreservesSiblings(t *testing.T) {
	p := filepath.Join(t.TempDir(), "config.toml")
	require.NoError(t, os.WriteFile(p, []byte(
		"[mcp_servers.other]\ncommand = \"other\"\n\n[mcp_servers.cq]\ncommand = \"/bin/cq\"\n"), 0o644))
	c, err := removeTOMLSection(p, "mcp_servers.cq", false)
	require.NoError(t, err)
	require.Equal(t, ActionRemoved, c.Action)

	got, err := os.ReadFile(p)
	require.NoError(t, err)
	require.Contains(t, string(got), "[mcp_servers.other]")
	require.NotContains(t, string(got), "[mcp_servers.cq]")
}

func TestRemoveTOMLSectionAbsentFileIsUnchanged(t *testing.T) {
	p := filepath.Join(t.TempDir(), "config.toml")
	c, err := removeTOMLSection(p, "mcp_servers.cq", false)
	require.NoError(t, err)
	require.Equal(t, ActionUnchanged, c.Action)
}

func TestRemoveTOMLSectionAbsentKeyIsUnchanged(t *testing.T) {
	p := filepath.Join(t.TempDir(), "config.toml")
	require.NoError(t, os.WriteFile(p, []byte("[other]\nkey = \"val\"\n"), 0o644))
	c, err := removeTOMLSection(p, "mcp_servers.cq", false)
	require.NoError(t, err)
	require.Equal(t, ActionUnchanged, c.Action)
}

func TestUpsertTOMLSectionRejectsNonTableIntermediate(t *testing.T) {
	p := filepath.Join(t.TempDir(), "config.toml")
	require.NoError(t, os.WriteFile(p, []byte("mcp_servers = \"not a table\"\n"), 0o644))
	_, err := upsertTOMLSection(p, "mcp_servers.cq", map[string]any{"command": "/bin/cq"}, false)
	require.Error(t, err)
	require.Contains(t, err.Error(), "not a table")
}

func TestUpsertTOMLSectionRejectsNonTableLeaf(t *testing.T) {
	p := filepath.Join(t.TempDir(), "config.toml")
	require.NoError(t, os.WriteFile(p, []byte("[mcp_servers]\ncq = \"not a table\"\n"), 0o644))
	_, err := upsertTOMLSection(p, "mcp_servers.cq", map[string]any{"command": "/bin/cq"}, false)
	require.Error(t, err)
	require.Contains(t, err.Error(), "not a table")
}

func TestUpsertTOMLSectionRejectsBlankSegment(t *testing.T) {
	p := filepath.Join(t.TempDir(), "config.toml")
	_, err := upsertTOMLSection(p, "a..b", map[string]any{"key": "val"}, false)
	require.Error(t, err)
	require.Contains(t, err.Error(), "empty segment")
}

func TestRemoveTOMLSectionRejectsBlankSegment(t *testing.T) {
	p := filepath.Join(t.TempDir(), "config.toml")
	_, err := removeTOMLSection(p, "", false)
	require.Error(t, err)
	require.Contains(t, err.Error(), "must not be empty")
}
