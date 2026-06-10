package discovery

import (
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestCacheReturnsMissForUnknownAddr(t *testing.T) {
	t.Parallel()

	c := newCache(t.TempDir(), time.Hour)
	_, ok := c.get("https://example.com")
	require.False(t, ok)
}

func TestCacheReturnsHitWithinTTL(t *testing.T) {
	t.Parallel()

	c := newCache(t.TempDir(), time.Hour)
	info := NodeInfo{Version: 1, APIBaseURL: "https://api.example.com/api/v1", APIVersion: "v1"}
	require.NoError(t, c.put("https://example.com", info))

	got, ok := c.get("https://example.com")
	require.True(t, ok)
	require.Equal(t, info, got)
}

func TestCacheReturnsMissAfterTTL(t *testing.T) {
	t.Parallel()

	c := newCache(t.TempDir(), time.Millisecond)
	info := NodeInfo{Version: 1, APIBaseURL: "https://api.example.com/api/v1", APIVersion: "v1"}
	require.NoError(t, c.put("https://example.com", info))

	time.Sleep(5 * time.Millisecond)

	_, ok := c.get("https://example.com")
	require.False(t, ok)
}

func TestCacheInvalidateRemovesEntry(t *testing.T) {
	t.Parallel()

	c := newCache(t.TempDir(), time.Hour)
	info := NodeInfo{Version: 1, APIBaseURL: "https://api.example.com/api/v1", APIVersion: "v1"}
	require.NoError(t, c.put("https://example.com", info))
	require.NoError(t, c.invalidate("https://example.com"))

	_, ok := c.get("https://example.com")
	require.False(t, ok)
}

func TestCacheInvalidateIsNoOpForMissingEntry(t *testing.T) {
	t.Parallel()

	c := newCache(t.TempDir(), time.Hour)
	require.NoError(t, c.invalidate("https://example.com"))
}

func TestCachePutLeavesNoTempFiles(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	c := newCache(dir, time.Hour)

	info := NodeInfo{Version: 1, APIBaseURL: "https://api.example.com/api/v1", APIVersion: "v1"}
	require.NoError(t, c.put("https://example.com", info))

	files, err := filepath.Glob(filepath.Join(dir, "tmp-*"))
	require.NoError(t, err)
	require.Empty(t, files)
}

func TestCacheTreatsSchemaInvalidEntryAsMiss(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	c := newCache(dir, time.Hour)

	// Write a payload that decodes cleanly but does not satisfy the
	// current schema (missing version, bad api_version). Simulates a
	// manually-edited or stale-format cache file.
	p := c.pathFor("https://example.com")
	require.NoError(t, os.WriteFile(p, []byte(`{"api_base_url":"https://api.example.com","api_version":"v9"}`), 0o600))

	_, ok := c.get("https://example.com")
	require.False(t, ok)

	// Invalid entries are removed so the next lookup is a clean miss.
	_, err := os.Stat(p)
	require.True(t, os.IsNotExist(err))
}

func TestCacheTreatsUnknownFieldEntryAsMiss(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	c := newCache(dir, time.Hour)

	p := c.pathFor("https://example.com")
	require.NoError(t, os.WriteFile(p, []byte(`{"version":1,"api_base_url":"https://api.example.com/api/v1","api_version":"v1","mystery":"x"}`), 0o600))

	_, ok := c.get("https://example.com")
	require.False(t, ok)
}

func TestCacheTreatsTrailingContentEntryAsMiss(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	c := newCache(dir, time.Hour)

	p := c.pathFor("https://example.com")
	// Valid JSON object followed by stray content. The default
	// json.Decoder semantics would accept the first object and drop
	// the trailing bytes; decodeNodeInfo rejects it so a partially
	// corrupted cache file falls through to a clean re-probe.
	require.NoError(t, os.WriteFile(p, []byte(`{"version":1,"api_base_url":"https://api.example.com/api/v1","api_version":"v1"} garbage`), 0o600))

	_, ok := c.get("https://example.com")
	require.False(t, ok)

	_, err := os.Stat(p)
	require.True(t, os.IsNotExist(err))
}
