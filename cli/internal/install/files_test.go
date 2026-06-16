package install

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestWriteManagedFilesCreatesThenUnchanged(t *testing.T) {
	dir := t.TempDir()
	files := map[string]string{"cq/SKILL.md": "body"}

	c1, err := writeManagedFiles(dir, files, false)
	require.NoError(t, err)
	require.Equal(t, ActionCreated, c1.Action)
	body, err := os.ReadFile(filepath.Join(dir, "cq", "SKILL.md"))
	require.NoError(t, err)
	require.Equal(t, "body", string(body))

	c2, err := writeManagedFiles(dir, files, false)
	require.NoError(t, err)
	require.Equal(t, ActionUnchanged, c2.Action)
}

func TestWriteManagedFilesPrunesStale(t *testing.T) {
	dir := t.TempDir()
	_, err := writeManagedFiles(dir, map[string]string{"a.md": "x", "b.md": "y"}, false)
	require.NoError(t, err)
	_, err = writeManagedFiles(dir, map[string]string{"a.md": "x"}, false)
	require.NoError(t, err)
	_, err = os.Stat(filepath.Join(dir, "b.md"))
	require.True(t, os.IsNotExist(err))
}

func TestRemoveManagedFilesSkipsUserModified(t *testing.T) {
	dir := t.TempDir()
	_, err := writeManagedFiles(dir, map[string]string{"cq/SKILL.md": "body"}, false)
	require.NoError(t, err)
	require.NoError(t, os.WriteFile(filepath.Join(dir, "cq", "SKILL.md"), []byte("edited"), 0o644))

	c, err := removeManagedFiles(dir, false)
	require.NoError(t, err)
	require.Equal(t, ActionSkipped, c.Action)
	_, err = os.Stat(filepath.Join(dir, "cq", "SKILL.md"))
	require.NoError(t, err)
}

func TestRemoveManagedFilesRemovesClean(t *testing.T) {
	dir := t.TempDir()
	_, err := writeManagedFiles(dir, map[string]string{"cq/SKILL.md": "body"}, false)
	require.NoError(t, err)

	c, err := removeManagedFiles(dir, false)
	require.NoError(t, err)
	require.Equal(t, ActionRemoved, c.Action)
	_, err = os.Stat(filepath.Join(dir, "cq", "SKILL.md"))
	require.True(t, os.IsNotExist(err))
}

func TestWriteManagedFilesKeepsUserModifiedStale(t *testing.T) {
	dir := t.TempDir()
	_, err := writeManagedFiles(dir, map[string]string{"a.md": "x", "b.md": "y"}, false)
	require.NoError(t, err)
	// The user edits b.md, then a re-install drops it from the set.
	require.NoError(t, os.WriteFile(filepath.Join(dir, "b.md"), []byte("edited"), 0o644))
	c, err := writeManagedFiles(dir, map[string]string{"a.md": "x"}, false)
	require.NoError(t, err)
	require.Equal(t, ActionSkipped, c.Action)
	body, err := os.ReadFile(filepath.Join(dir, "b.md"))
	require.NoError(t, err)
	require.Equal(t, "edited", string(body))
}

func TestSafeJoinRejectsEscape(t *testing.T) {
	_, err := safeJoin("/home/dev/.agents/skills", "../../etc/shadow")
	require.Error(t, err)
	got, err := safeJoin("/home/dev/.agents/skills", "cq/SKILL.md")
	require.NoError(t, err)
	require.Equal(t, filepath.Join("/home/dev/.agents/skills", "cq", "SKILL.md"), got)
}

func TestWriteManagedFilesKeepsUserModified(t *testing.T) {
	dir := t.TempDir()
	files := map[string]string{"cq/SKILL.md": "body"}
	_, err := writeManagedFiles(dir, files, false)
	require.NoError(t, err)

	// The user edits the installed skill, then re-runs install.
	require.NoError(t, os.WriteFile(filepath.Join(dir, "cq", "SKILL.md"), []byte("hacked"), 0o644))
	c, err := writeManagedFiles(dir, files, false)
	require.NoError(t, err)
	require.Equal(t, ActionSkipped, c.Action)
	body, err := os.ReadFile(filepath.Join(dir, "cq", "SKILL.md"))
	require.NoError(t, err)
	require.Equal(t, "hacked", string(body))
}

func TestWriteManagedFilesDoesNotAdoptPreexisting(t *testing.T) {
	dir := t.TempDir()
	require.NoError(t, os.MkdirAll(filepath.Join(dir, "cq"), 0o755))
	// A file with our exact content exists before any install.
	require.NoError(t, os.WriteFile(filepath.Join(dir, "cq", "SKILL.md"), []byte("body"), 0o644))

	c, err := writeManagedFiles(dir, map[string]string{"cq/SKILL.md": "body"}, false)
	require.NoError(t, err)
	require.Equal(t, ActionSkipped, c.Action)
	// We never wrote it, so we do not claim it: no manifest, nothing for
	// uninstall to remove.
	require.NoFileExists(t, filepath.Join(dir, manifestName))
}
