package auth

import (
	"bytes"
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/mozilla-ai/cq/cli/internal/credstore"
)

func TestStatus_NotSignedInReturnsErrNotFound(t *testing.T) {
	store := newMemStore()
	out := &bytes.Buffer{}

	err := Status(context.Background(), StatusConfig{Store: store, Out: out})
	require.ErrorIs(t, err, credstore.ErrNotFound)
	require.Contains(t, out.String(), "Not signed in")
}

func TestStatus_SignedInRendersIdentityAndServer(t *testing.T) {
	store := newMemStore()
	require.NoError(t, store.Save(credstore.Credentials{SessionJWT: "j", Username: "alice"}))

	out := &bytes.Buffer{}

	err := Status(context.Background(), StatusConfig{
		Store:  store,
		Server: "https://cq.example.com",
		Out:    out,
	})
	require.NoError(t, err)
	require.Contains(t, out.String(), "https://cq.example.com")
	require.Contains(t, out.String(), "alice")
}

func TestStatus_RendersExpiryWhenKnown(t *testing.T) {
	store := newMemStore()
	expiry := time.Date(2026, 6, 1, 12, 0, 0, 0, time.UTC)
	require.NoError(t, store.Save(credstore.Credentials{
		SessionJWT:       "j",
		Username:         "alice",
		SessionExpiresAt: expiry,
	}))

	out := &bytes.Buffer{}

	require.NoError(t, Status(context.Background(), StatusConfig{Store: store, Out: out}))
	require.Contains(t, out.String(), expiry.Format(time.RFC3339))
}

func TestStatus_OmitsExpiryWhenZero(t *testing.T) {
	store := newMemStore()
	require.NoError(t, store.Save(credstore.Credentials{SessionJWT: "j", Username: "alice"}))

	out := &bytes.Buffer{}

	require.NoError(t, Status(context.Background(), StatusConfig{Store: store, Out: out}))
	require.NotContains(t, out.String(), "Expires:")
}
