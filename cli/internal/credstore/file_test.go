package credstore

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestNewFileStore_RejectsEmptyDir(t *testing.T) {
	_, err := newFileStore("")
	require.Error(t, err)
}

func TestFileStore_Load_MissingReturnsErrNotFound(t *testing.T) {
	store, err := newFileStore(t.TempDir())
	require.NoError(t, err)

	_, err = store.Load()
	require.ErrorIs(t, err, ErrNotFound)
}

func TestFileStore_SaveThenLoad_Roundtrips(t *testing.T) {
	store, err := newFileStore(t.TempDir())
	require.NoError(t, err)

	want := Credentials{
		SessionJWT:       "jwt-value",
		SessionExpiresAt: time.Date(2026, 1, 2, 3, 4, 5, 0, time.UTC),
		Username:         "alice",
	}
	require.NoError(t, store.Save(want))

	got, err := store.Load()
	require.NoError(t, err)
	require.Equal(t, want, got)
}

func TestFileStore_Save_FilePermissionsAre0600(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("POSIX permissions not enforced on Windows")
	}

	dir := t.TempDir()
	store, err := newFileStore(dir)
	require.NoError(t, err)

	require.NoError(t, store.Save(Credentials{SessionJWT: "j", Username: "u"}))

	info, err := os.Stat(filepath.Join(dir, credentialsFilename))
	require.NoError(t, err)
	require.Equal(t, credentialsFileMode, info.Mode().Perm())
}

func TestFileStore_Save_DirectoryCreatedWith0700(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("POSIX permissions not enforced on Windows")
	}

	dir := filepath.Join(t.TempDir(), "nested", "cq")
	store, err := newFileStore(dir)
	require.NoError(t, err)

	require.NoError(t, store.Save(Credentials{SessionJWT: "j", Username: "u"}))

	info, err := os.Stat(dir)
	require.NoError(t, err)
	require.Equal(t, credentialsDirMode, info.Mode().Perm())
}

func TestFileStore_DeleteAfterSave_RemovesCredentials(t *testing.T) {
	store, err := newFileStore(t.TempDir())
	require.NoError(t, err)

	require.NoError(t, store.Save(Credentials{SessionJWT: "j", Username: "u"}))
	require.NoError(t, store.Delete())

	_, err = store.Load()
	require.ErrorIs(t, err, ErrNotFound)
}

func TestFileStore_DeleteWhenAbsent_NoError(t *testing.T) {
	store, err := newFileStore(t.TempDir())
	require.NoError(t, err)

	require.NoError(t, store.Delete())
}

func TestFileStore_Load_CorruptJSONReturnsError(t *testing.T) {
	dir := t.TempDir()
	require.NoError(t, os.WriteFile(filepath.Join(dir, credentialsFilename), []byte("not json"), credentialsFileMode))

	store, err := newFileStore(dir)
	require.NoError(t, err)

	_, err = store.Load()
	require.Error(t, err)
	require.False(t, errors.Is(err, ErrNotFound))

	var syntaxErr *json.SyntaxError
	require.ErrorAs(t, err, &syntaxErr)
}
