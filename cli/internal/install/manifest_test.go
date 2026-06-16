package install

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestHashFileIsStable(t *testing.T) {
	p := filepath.Join(t.TempDir(), "f.txt")
	require.NoError(t, os.WriteFile(p, []byte("hello"), 0o644))
	h1, err := hashFile(p)
	require.NoError(t, err)
	h2, err := hashFile(p)
	require.NoError(t, err)
	require.Equal(t, h1, h2)
	require.Len(t, h1, 64)
}

func TestManifestRoundTrip(t *testing.T) {
	dir := t.TempDir()
	mp := filepath.Join(dir, ".cq-install-manifest.json")
	require.NoError(t, writeManifest(mp, []manifestEntry{{Path: "cq/SKILL.md", SHA256: "abc"}}))
	got, err := loadManifest(mp)
	require.NoError(t, err)
	require.NotNil(t, got)
	require.Equal(t, "cq/SKILL.md", got.Files[0].Path)
}

func TestLoadManifestMissingIsNil(t *testing.T) {
	got, err := loadManifest(filepath.Join(t.TempDir(), "nope.json"))
	require.NoError(t, err)
	require.Nil(t, got)
}
