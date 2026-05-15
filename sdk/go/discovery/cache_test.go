package discovery

import (
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
	info := NodeInfo{APIBaseURL: "https://api.example.com/api/v1", APIVersion: "v1"}
	require.NoError(t, c.put("https://example.com", info))

	got, ok := c.get("https://example.com")
	require.True(t, ok)
	require.Equal(t, info, got)
}

func TestCacheReturnsMissAfterTTL(t *testing.T) {
	t.Parallel()

	c := newCache(t.TempDir(), time.Millisecond)
	info := NodeInfo{APIBaseURL: "https://api.example.com/api/v1", APIVersion: "v1"}
	require.NoError(t, c.put("https://example.com", info))

	time.Sleep(5 * time.Millisecond)

	_, ok := c.get("https://example.com")
	require.False(t, ok)
}

func TestCacheInvalidateRemovesEntry(t *testing.T) {
	t.Parallel()

	c := newCache(t.TempDir(), time.Hour)
	info := NodeInfo{APIBaseURL: "https://api.example.com/api/v1", APIVersion: "v1"}
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

	info := NodeInfo{APIBaseURL: "https://api.example.com/api/v1", APIVersion: "v1"}
	require.NoError(t, c.put("https://example.com", info))

	files, err := filepath.Glob(filepath.Join(dir, "tmp-*"))
	require.NoError(t, err)
	require.Empty(t, files)
}
