package install

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

var testMarkers = blockMarkers{start: "<!-- cq:start -->", end: "<!-- cq:end -->"}

func TestUpsertMarkdownBlockCreatesFile(t *testing.T) {
	p := filepath.Join(t.TempDir(), "AGENTS.md")
	c, err := upsertMarkdownBlock(p, testMarkers,
		"<!-- cq:start -->\n## CQ\n<!-- cq:end -->", false)
	require.NoError(t, err)
	require.Equal(t, ActionCreated, c.Action)
	got, err := os.ReadFile(p)
	require.NoError(t, err)
	require.Equal(t, "<!-- cq:start -->\n## CQ\n<!-- cq:end -->\n", string(got))
}

func TestUpsertMarkdownBlockAppendsToExisting(t *testing.T) {
	p := filepath.Join(t.TempDir(), "AGENTS.md")
	require.NoError(t, os.WriteFile(p, []byte("# My Agents\n\nExisting content.\n"), 0o644))
	c, err := upsertMarkdownBlock(p, testMarkers,
		"<!-- cq:start -->\n## CQ\n<!-- cq:end -->", false)
	require.NoError(t, err)
	require.Equal(t, ActionUpdated, c.Action)
	got, err := os.ReadFile(p)
	require.NoError(t, err)
	require.Equal(t, "# My Agents\n\nExisting content.\n\n<!-- cq:start -->\n## CQ\n<!-- cq:end -->\n", string(got))
}

func TestUpsertMarkdownBlockIsIdempotent(t *testing.T) {
	p := filepath.Join(t.TempDir(), "AGENTS.md")
	block := "<!-- cq:start -->\n## CQ\n<!-- cq:end -->"
	_, err := upsertMarkdownBlock(p, testMarkers, block, false)
	require.NoError(t, err)
	c, err := upsertMarkdownBlock(p, testMarkers, block, false)
	require.NoError(t, err)
	require.Equal(t, ActionUnchanged, c.Action)
}

func TestUpsertMarkdownBlockReplacesChanged(t *testing.T) {
	p := filepath.Join(t.TempDir(), "AGENTS.md")
	require.NoError(t, os.WriteFile(p,
		[]byte("preamble\n\n<!-- cq:start -->\nold body\n<!-- cq:end -->\n\npostamble\n"), 0o644))
	c, err := upsertMarkdownBlock(p, testMarkers,
		"<!-- cq:start -->\nnew body\n<!-- cq:end -->", false)
	require.NoError(t, err)
	require.Equal(t, ActionUpdated, c.Action)
	got, err := os.ReadFile(p)
	require.NoError(t, err)
	require.Equal(t, "preamble\n\n<!-- cq:start -->\nnew body\n<!-- cq:end -->\n\npostamble\n", string(got))
}

func TestUpsertMarkdownBlockSkipsMalformed(t *testing.T) {
	p := filepath.Join(t.TempDir(), "AGENTS.md")
	require.NoError(t, os.WriteFile(p, []byte("<!-- cq:start -->\nno end marker\n"), 0o644))
	c, err := upsertMarkdownBlock(p, testMarkers,
		"<!-- cq:start -->\nbody\n<!-- cq:end -->", false)
	require.NoError(t, err)
	require.Equal(t, ActionSkipped, c.Action)
}

func TestUpsertMarkdownBlockIgnoresStrayEndMarkerBeforeBlock(t *testing.T) {
	p := filepath.Join(t.TempDir(), "AGENTS.md")
	require.NoError(t, os.WriteFile(p, []byte(
		"intro <!-- cq:end --> note\n\n<!-- cq:start -->\nold\n<!-- cq:end -->\n"), 0o644))
	c, err := upsertMarkdownBlock(p, testMarkers, "<!-- cq:start -->\nnew\n<!-- cq:end -->", false)
	require.NoError(t, err)
	require.Equal(t, ActionUpdated, c.Action)
	got, err := os.ReadFile(p)
	require.NoError(t, err)
	require.Contains(t, string(got), "<!-- cq:start -->\nnew\n<!-- cq:end -->")
	require.Contains(t, string(got), "intro <!-- cq:end --> note")
}

func TestUpsertMarkdownBlockDryRunWritesNothing(t *testing.T) {
	p := filepath.Join(t.TempDir(), "AGENTS.md")
	c, err := upsertMarkdownBlock(p, testMarkers,
		"<!-- cq:start -->\nbody\n<!-- cq:end -->", true)
	require.NoError(t, err)
	require.Equal(t, ActionCreated, c.Action)
	_, statErr := os.Stat(p)
	require.True(t, os.IsNotExist(statErr))
}

func TestRemoveMarkdownBlockDeletesBlock(t *testing.T) {
	p := filepath.Join(t.TempDir(), "AGENTS.md")
	require.NoError(t, os.WriteFile(p,
		[]byte("preamble\n\n<!-- cq:start -->\ncq block\n<!-- cq:end -->\n\npostamble\n"), 0o644))
	c, err := removeMarkdownBlock(p, testMarkers, false)
	require.NoError(t, err)
	require.Equal(t, ActionRemoved, c.Action)
	got, err := os.ReadFile(p)
	require.NoError(t, err)
	require.Equal(t, "preamble\n\npostamble\n", string(got))
}

func TestRemoveMarkdownBlockDeletesFileWhenEmpty(t *testing.T) {
	p := filepath.Join(t.TempDir(), "AGENTS.md")
	require.NoError(t, os.WriteFile(p,
		[]byte("<!-- cq:start -->\ncq block\n<!-- cq:end -->\n"), 0o644))
	c, err := removeMarkdownBlock(p, testMarkers, false)
	require.NoError(t, err)
	require.Equal(t, ActionRemoved, c.Action)
	_, statErr := os.Stat(p)
	require.True(t, os.IsNotExist(statErr))
}

func TestRemoveMarkdownBlockAbsentFileIsUnchanged(t *testing.T) {
	p := filepath.Join(t.TempDir(), "AGENTS.md")
	c, err := removeMarkdownBlock(p, testMarkers, false)
	require.NoError(t, err)
	require.Equal(t, ActionUnchanged, c.Action)
}

func TestRemoveMarkdownBlockAbsentMarkerIsUnchanged(t *testing.T) {
	p := filepath.Join(t.TempDir(), "AGENTS.md")
	require.NoError(t, os.WriteFile(p, []byte("# Agents\n\nNo cq block here.\n"), 0o644))
	c, err := removeMarkdownBlock(p, testMarkers, false)
	require.NoError(t, err)
	require.Equal(t, ActionUnchanged, c.Action)
}

func TestRemoveMarkdownBlockSkipsMalformed(t *testing.T) {
	p := filepath.Join(t.TempDir(), "AGENTS.md")
	require.NoError(t, os.WriteFile(p, []byte("<!-- cq:start -->\nno end\n"), 0o644))
	c, err := removeMarkdownBlock(p, testMarkers, false)
	require.NoError(t, err)
	require.Equal(t, ActionSkipped, c.Action)
}
