package discovery

import (
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestDefaultCacheDirUsesXDGCacheHomeWhenAbsolute(t *testing.T) {
	xdg := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", xdg)

	got, err := DefaultCacheDir()
	require.NoError(t, err)
	require.Equal(t, filepath.Join(xdg, "cq", "discovery"), got)
}

func TestDefaultCacheDirRejectsRelativeXDGCacheHome(t *testing.T) {
	t.Setenv("XDG_CACHE_HOME", "relative/path")

	_, err := DefaultCacheDir()
	require.Error(t, err)
	require.Contains(t, err.Error(), "absolute")
}

func TestDefaultCacheDirTreatsWhitespaceOnlyXDGCacheHomeAsUnset(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("XDG_CACHE_HOME", "   ")

	got, err := DefaultCacheDir()
	require.NoError(t, err)
	require.Equal(t, filepath.Join(home, ".cache", "cq", "discovery"), got)
}

func TestDefaultCacheDirFallsBackToHomeWhenXDGUnset(t *testing.T) {
	t.Setenv("XDG_CACHE_HOME", "")
	home := t.TempDir()
	t.Setenv("HOME", home)

	got, err := DefaultCacheDir()
	require.NoError(t, err)
	require.Equal(t, filepath.Join(home, ".cache", "cq", "discovery"), got)
}
