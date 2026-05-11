package credstore

import (
	"errors"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"github.com/zalando/go-keyring"
)

// resetKeyringMock initialises the zalando in-memory keyring before each test
// so state from one test does not leak into another.
func resetKeyringMock(t *testing.T) {
	t.Helper()

	keyring.MockInit()
}

func TestKeyringStore_Load_MissingReturnsErrNotFound(t *testing.T) {
	resetKeyringMock(t)

	store := newKeyringStore()

	_, err := store.Load()
	require.ErrorIs(t, err, ErrNotFound)
}

func TestKeyringStore_SaveThenLoad_Roundtrips(t *testing.T) {
	resetKeyringMock(t)

	store := newKeyringStore()

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

func TestKeyringStore_DeleteAfterSave_RemovesCredentials(t *testing.T) {
	resetKeyringMock(t)

	store := newKeyringStore()
	require.NoError(t, store.Save(Credentials{SessionJWT: "j", Username: "u"}))
	require.NoError(t, store.Delete())

	_, err := store.Load()
	require.ErrorIs(t, err, ErrNotFound)
}

func TestKeyringStore_DeleteWhenAbsent_NoError(t *testing.T) {
	resetKeyringMock(t)

	store := newKeyringStore()
	require.NoError(t, store.Delete())
}

func TestKeyringStore_Save_BackendErrorIsReturned(t *testing.T) {
	want := errors.New("backend boom")

	keyring.MockInitWithError(want)
	t.Cleanup(keyring.MockInit)

	store := newKeyringStore()
	err := store.Save(Credentials{SessionJWT: "j", Username: "u"})
	require.ErrorIs(t, err, want)
}

func TestKeyringStore_Load_BackendErrorIsReturned(t *testing.T) {
	want := errors.New("backend boom")

	keyring.MockInitWithError(want)
	t.Cleanup(keyring.MockInit)

	store := newKeyringStore()
	_, err := store.Load()
	require.ErrorIs(t, err, want)
	require.False(t, errors.Is(err, ErrNotFound))
}

func TestKeyringStore_Load_CorruptValueReturnsError(t *testing.T) {
	resetKeyringMock(t)

	require.NoError(t, keyring.Set(keyringService, keyringAccount, "not json"))

	store := newKeyringStore()
	_, err := store.Load()
	require.Error(t, err)
	require.False(t, errors.Is(err, ErrNotFound))
}
