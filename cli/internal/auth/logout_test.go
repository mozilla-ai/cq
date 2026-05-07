package auth

import (
	"bytes"
	"context"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/mozilla-ai/cq/cli/internal/credstore"
)

func TestLogout_RemovesStoredCredentials(t *testing.T) {
	store := newMemStore()
	require.NoError(t, store.Save(credstore.Credentials{SessionJWT: "j", Username: "alice"}))

	out := &bytes.Buffer{}

	require.NoError(t, Logout(context.Background(), LogoutConfig{Store: store, Out: out}))

	_, err := store.Load()
	require.ErrorIs(t, err, credstore.ErrNotFound)
	require.Contains(t, out.String(), "Signed out")
}

func TestLogout_NotSignedInIsIdempotent(t *testing.T) {
	store := newMemStore()
	out := &bytes.Buffer{}

	require.NoError(t, Logout(context.Background(), LogoutConfig{Store: store, Out: out}))
	require.Contains(t, out.String(), "Signed out")
}
