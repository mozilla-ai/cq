package credstore

import (
	"errors"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/zalando/go-keyring"
)

func TestNew_WhenKeyringHealthy_ReturnsKeyringBackedStore(t *testing.T) {
	keyring.MockInit()

	store, err := New(t.TempDir())
	require.NoError(t, err)

	_, ok := store.(*keyringStore)
	require.True(t, ok, "expected keyringStore, got %T", store)
}

func TestNew_WhenKeyringBroken_ReturnsFileBackedStore(t *testing.T) {
	keyring.MockInitWithError(errors.New("dbus unavailable"))
	t.Cleanup(keyring.MockInit)

	store, err := New(t.TempDir())
	require.NoError(t, err)

	_, ok := store.(*fileStore)
	require.True(t, ok, "expected fileStore, got %T", store)
}

func TestNew_FileBackedStore_WritesUnderSuppliedDir(t *testing.T) {
	keyring.MockInitWithError(errors.New("dbus unavailable"))
	t.Cleanup(keyring.MockInit)

	dir := t.TempDir()
	store, err := New(dir)
	require.NoError(t, err)

	require.NoError(t, store.Save(Credentials{SessionJWT: "j", Username: "u"}))

	_, err = os.Stat(filepath.Join(dir, credentialsFilename))
	require.NoError(t, err)
}

func TestNew_RejectsEmptyFileDirWhenKeyringBroken(t *testing.T) {
	keyring.MockInitWithError(errors.New("dbus unavailable"))
	t.Cleanup(keyring.MockInit)

	_, err := New("")
	require.Error(t, err)
}
