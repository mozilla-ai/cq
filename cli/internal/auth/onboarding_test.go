package auth

import (
	"bufio"
	"bytes"
	"context"
	"errors"
	"io"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

// stubAuthClient is a Client whose methods are scripted via per-method
// function fields. Methods left nil panic when called, surfacing
// unexpected interactions in tests.
type stubAuthClient struct {
	oauthProviders      func(ctx context.Context) ([]Provider, error)
	oauthNativeStart    func(ctx context.Context, req NativeStartRequest) (string, error)
	oauthNativeExchange func(ctx context.Context, req NativeExchangeRequest) (string, error)
	me                  func(ctx context.Context, jwt string) (User, error)
	claimUsername       func(ctx context.Context, jwt, username string) (User, error)
	createAPIKey        func(ctx context.Context, jwt string, req CreateAPIKeyRequest) (CreatedAPIKey, error)
	listAPIKeys         func(ctx context.Context, jwt string) ([]APIKey, error)
	revokeAPIKey        func(ctx context.Context, jwt string, keyID string) error
}

func (s *stubAuthClient) OAuthProviders(ctx context.Context) ([]Provider, error) {
	if s.oauthProviders == nil {
		panic("OAuthProviders not stubbed")
	}

	return s.oauthProviders(ctx)
}

func (s *stubAuthClient) OAuthNativeStart(ctx context.Context, req NativeStartRequest) (string, error) {
	if s.oauthNativeStart == nil {
		panic("OAuthNativeStart not stubbed")
	}

	return s.oauthNativeStart(ctx, req)
}

func (s *stubAuthClient) OAuthNativeExchange(ctx context.Context, req NativeExchangeRequest) (string, error) {
	if s.oauthNativeExchange == nil {
		panic("OAuthNativeExchange not stubbed")
	}

	return s.oauthNativeExchange(ctx, req)
}

func (s *stubAuthClient) Me(ctx context.Context, jwt string) (User, error) {
	if s.me == nil {
		panic("Me not stubbed")
	}

	return s.me(ctx, jwt)
}

func (s *stubAuthClient) ClaimUsername(ctx context.Context, jwt, username string) (User, error) {
	if s.claimUsername == nil {
		panic("ClaimUsername not stubbed")
	}

	return s.claimUsername(ctx, jwt, username)
}

func (s *stubAuthClient) CreateAPIKey(ctx context.Context, jwt string, req CreateAPIKeyRequest) (CreatedAPIKey, error) {
	if s.createAPIKey == nil { // pragma: allowlist secret
		panic("CreateAPIKey not stubbed")
	}

	return s.createAPIKey(ctx, jwt, req)
}

func (s *stubAuthClient) ListAPIKeys(ctx context.Context, jwt string) ([]APIKey, error) {
	if s.listAPIKeys == nil { // pragma: allowlist secret
		panic("ListAPIKeys not stubbed")
	}

	return s.listAPIKeys(ctx, jwt)
}

func (s *stubAuthClient) RevokeAPIKey(ctx context.Context, jwt string, keyID string) error {
	if s.revokeAPIKey == nil { // pragma: allowlist secret
		panic("RevokeAPIKey not stubbed")
	}

	return s.revokeAPIKey(ctx, jwt, keyID)
}

func TestClaimUsernameInteractively_FirstAttemptSucceeds(t *testing.T) {
	client := &stubAuthClient{
		claimUsername: func(_ context.Context, jwt, username string) (User, error) {
			require.Equal(t, "test-jwt", jwt)
			require.Equal(t, "alice", username)

			return User{Username: "alice"}, nil
		},
	}

	out := &bytes.Buffer{}
	scanner := bufio.NewScanner(strings.NewReader("alice\n"))

	got, err := claimUsernameInteractively(context.Background(), scanner, out, client, "test-jwt")
	require.NoError(t, err)
	require.Equal(t, "alice", got.Username)
	require.Contains(t, out.String(), "Username")
}

func TestClaimUsernameInteractively_RetriesOnUnavailableAndShowsSuggestions(t *testing.T) {
	calls := 0

	client := &stubAuthClient{
		claimUsername: func(_ context.Context, _, username string) (User, error) {
			calls++
			if calls == 1 {
				require.Equal(t, "alice", username)

				return User{}, &UsernameUnavailableError{Suggestions: []string{"alice1", "alice_dev"}}
			}

			require.Equal(t, "alice_dev", username)

			return User{Username: "alice_dev"}, nil
		},
	}

	out := &bytes.Buffer{}
	scanner := bufio.NewScanner(strings.NewReader("alice\nalice_dev\n"))

	got, err := claimUsernameInteractively(context.Background(), scanner, out, client, "jwt")
	require.NoError(t, err)
	require.Equal(t, "alice_dev", got.Username)
	require.Equal(t, 2, calls)
	require.Contains(t, out.String(), "alice1")
	require.Contains(t, out.String(), "alice_dev")
}

func TestClaimUsernameInteractively_RetriesOnInvalidFormatAndShowsDetail(t *testing.T) {
	calls := 0

	client := &stubAuthClient{
		claimUsername: func(_ context.Context, _, username string) (User, error) {
			calls++
			if calls == 1 {
				return User{}, &UsernameFormatError{Detail: "must start with a letter"}
			}

			return User{Username: username}, nil
		},
	}

	out := &bytes.Buffer{}
	scanner := bufio.NewScanner(strings.NewReader("1bad\nalice\n"))

	got, err := claimUsernameInteractively(context.Background(), scanner, out, client, "jwt")
	require.NoError(t, err)
	require.Equal(t, "alice", got.Username)
	require.Equal(t, 2, calls)
	require.Contains(t, out.String(), "must start with a letter")
}

func TestClaimUsernameInteractively_PropagatesRateLimitError(t *testing.T) {
	client := &stubAuthClient{
		claimUsername: func(_ context.Context, _, _ string) (User, error) {
			return User{}, &RateLimitedError{RetryAfter: 60 * time.Second}
		},
	}

	scanner := bufio.NewScanner(strings.NewReader("alice\n"))
	_, err := claimUsernameInteractively(context.Background(), scanner, &bytes.Buffer{}, client, "jwt")

	var rate *RateLimitedError
	require.ErrorAs(t, err, &rate)
	require.Equal(t, 60*time.Second, rate.RetryAfter)
}

func TestClaimUsernameInteractively_PropagatesUnexpectedError(t *testing.T) {
	want := errors.New("upstream boom")

	client := &stubAuthClient{
		claimUsername: func(_ context.Context, _, _ string) (User, error) {
			return User{}, want
		},
	}

	scanner := bufio.NewScanner(strings.NewReader("alice\n"))
	_, err := claimUsernameInteractively(context.Background(), scanner, &bytes.Buffer{}, client, "jwt")
	require.ErrorIs(t, err, want)
}

func TestClaimUsernameInteractively_RejectsEmptyInputWithoutCallingServer(t *testing.T) {
	calls := 0

	client := &stubAuthClient{
		claimUsername: func(_ context.Context, _, username string) (User, error) {
			calls++

			return User{Username: username}, nil
		},
	}

	scanner := bufio.NewScanner(strings.NewReader("\nalice\n"))
	got, err := claimUsernameInteractively(context.Background(), scanner, &bytes.Buffer{}, client, "jwt")
	require.NoError(t, err)
	require.Equal(t, "alice", got.Username)
	require.Equal(t, 1, calls)
}

func TestClaimUsernameInteractively_FailsOnEOF(t *testing.T) {
	client := &stubAuthClient{
		claimUsername: func(_ context.Context, _, _ string) (User, error) {
			t.Fatal("ClaimUsername should not be called when input is exhausted")

			return User{}, nil
		},
	}

	scanner := bufio.NewScanner(strings.NewReader(""))
	_, err := claimUsernameInteractively(context.Background(), scanner, &bytes.Buffer{}, client, "jwt")
	require.Error(t, err)
	require.ErrorIs(t, err, io.EOF)
}
