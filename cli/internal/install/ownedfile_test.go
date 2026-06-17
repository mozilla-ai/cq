package install

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestWriteIfMissingCreatesThenLeavesUserEdits(t *testing.T) {
	p := filepath.Join(t.TempDir(), "rules", "cq.mdc")

	c, err := writeIfMissing(p, "managed body\n", false)
	require.NoError(t, err)
	require.Equal(t, ActionCreated, c.Action)
	got, err := os.ReadFile(p)
	require.NoError(t, err)
	require.Equal(t, "managed body\n", string(got))

	// A second call with the same content is a no-op.
	c, err = writeIfMissing(p, "managed body\n", false)
	require.NoError(t, err)
	require.Equal(t, ActionUnchanged, c.Action)

	// A user edit is never clobbered, even with different desired content.
	require.NoError(t, os.WriteFile(p, []byte("user edit\n"), 0o644))
	c, err = writeIfMissing(p, "managed body\n", false)
	require.NoError(t, err)
	require.Equal(t, ActionUnchanged, c.Action)
	got, err = os.ReadFile(p)
	require.NoError(t, err)
	require.Equal(t, "user edit\n", string(got))
}

func TestWriteIfMissingDryRunWritesNothing(t *testing.T) {
	p := filepath.Join(t.TempDir(), "rules", "cq.mdc")
	c, err := writeIfMissing(p, "body\n", true)
	require.NoError(t, err)
	require.Equal(t, ActionCreated, c.Action)
	_, statErr := os.Stat(p)
	require.True(t, os.IsNotExist(statErr))
}

func TestRemoveOwnedFileHashGuards(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "cq.mdc")
	require.NoError(t, os.WriteFile(p, []byte("managed body\n"), 0o644))
	hash := sha256Hex("managed body\n")

	// Absent file: unchanged.
	c, err := removeOwnedFile(filepath.Join(dir, "absent.mdc"), hash, false)
	require.NoError(t, err)
	require.Equal(t, ActionUnchanged, c.Action)

	// Unmodified file: removed.
	c, err = removeOwnedFile(p, hash, false)
	require.NoError(t, err)
	require.Equal(t, ActionRemoved, c.Action)
	_, statErr := os.Stat(p)
	require.True(t, os.IsNotExist(statErr))
}

func TestRemoveOwnedFileLeavesUserModified(t *testing.T) {
	p := filepath.Join(t.TempDir(), "cq.mdc")
	require.NoError(t, os.WriteFile(p, []byte("user edit\n"), 0o644))
	c, err := removeOwnedFile(p, sha256Hex("managed body\n"), false)
	require.NoError(t, err)
	require.Equal(t, ActionSkipped, c.Action)
	_, statErr := os.Stat(p)
	require.NoError(t, statErr)
}
