package auth

import (
	"bytes"
	"context"
	"errors"
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

func TestLogout_RevokeNotSignedIn_DoesNotRequireClient(t *testing.T) {
	store := newMemStore()
	out := &bytes.Buffer{}

	require.NoError(t, Logout(context.Background(), LogoutConfig{Store: store, Revoke: true, Out: out}))
	require.Contains(t, out.String(), "already absent")
}

func TestLogout_RevokeSuccess_ClearsCredentials(t *testing.T) {
	store := newMemStore()
	require.NoError(t, store.Save(credstore.Credentials{SessionJWT: "j", Username: "alice"}))

	called := false
	client := &stubAuthClient{
		logout: func(_ context.Context, jwt string, allDevices bool) error {
			called = true
			require.Equal(t, "j", jwt)
			require.True(t, allDevices)

			return nil
		},
	}

	out := &bytes.Buffer{}

	require.NoError(t, Logout(context.Background(), LogoutConfig{
		Store:      store,
		Client:     client,
		Revoke:     true,
		AllDevices: true,
		Out:        out,
	}))
	require.True(t, called)
	require.Contains(t, out.String(), "server session revoked on all devices")

	_, err := store.Load()
	require.ErrorIs(t, err, credstore.ErrNotFound)
}

func TestLogout_RevokeFailure_PreservesCredentials(t *testing.T) {
	store := newMemStore()
	require.NoError(t, store.Save(credstore.Credentials{SessionJWT: "j", Username: "alice"}))

	client := &stubAuthClient{
		logout: func(context.Context, string, bool) error {
			return errors.New("upstream boom")
		},
	}

	err := Logout(context.Background(), LogoutConfig{
		Store:  store,
		Client: client,
		Revoke: true,
		Out:    &bytes.Buffer{},
	})
	require.Error(t, err)

	creds, loadErr := store.Load()
	require.NoError(t, loadErr)
	require.Equal(t, "j", creds.SessionJWT)
}

func TestLogout_RevokeExpiredSession_ClearsCredentials(t *testing.T) {
	store := newMemStore()
	require.NoError(t, store.Save(credstore.Credentials{SessionJWT: "j", Username: "alice"}))

	client := &stubAuthClient{
		logout: func(context.Context, string, bool) error {
			return ErrSessionExpired
		},
	}

	out := &bytes.Buffer{}
	require.NoError(t, Logout(context.Background(), LogoutConfig{
		Store:  store,
		Client: client,
		Revoke: true,
		Out:    out,
	}))
	require.Contains(t, out.String(), "could not be confirmed")

	_, err := store.Load()
	require.ErrorIs(t, err, credstore.ErrNotFound)
}
