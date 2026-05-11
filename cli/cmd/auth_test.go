package cmd

import (
	"bytes"
	"context"
	"errors"
	"sync"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/mozilla-ai/cq/cli/internal/auth"
	"github.com/mozilla-ai/cq/cli/internal/credstore"
)

// memStore is an in-memory credstore.Store used in cobra-level tests.
type memStore struct {
	sync.Mutex
	creds   credstore.Credentials
	hasData bool
}

func (s *memStore) Load() (credstore.Credentials, error) {
	s.Lock()
	defer s.Unlock()

	if !s.hasData {
		return credstore.Credentials{}, credstore.ErrNotFound
	}

	return s.creds, nil
}

func (s *memStore) Save(c credstore.Credentials) error {
	s.Lock()
	defer s.Unlock()

	s.creds = c
	s.hasData = true

	return nil
}

func (s *memStore) Delete() error {
	s.Lock()
	defer s.Unlock()

	s.creds = credstore.Credentials{}
	s.hasData = false

	return nil
}

// stubAuthClient is a cobra-test-local Client implementation: only
// the methods the tests need are stubbed; everything else panics so
// unexpected calls are obvious.
type stubAuthClient struct {
	oauthProviders func(ctx context.Context) ([]auth.Provider, error)
	createAPIKey   func(ctx context.Context, jwt string, req auth.CreateAPIKeyRequest) (auth.CreatedAPIKey, error)
	listAPIKeys    func(ctx context.Context, jwt string) ([]auth.APIKey, error)
	revokeAPIKey   func(ctx context.Context, jwt string, keyID string) error
}

func (s *stubAuthClient) OAuthProviders(ctx context.Context) ([]auth.Provider, error) {
	if s.oauthProviders == nil {
		panic("OAuthProviders not stubbed")
	}

	return s.oauthProviders(ctx)
}

func (s *stubAuthClient) OAuthNativeStart(context.Context, auth.NativeStartRequest) (string, error) {
	panic("OAuthNativeStart not stubbed")
}

func (s *stubAuthClient) OAuthNativeExchange(context.Context, auth.NativeExchangeRequest) (string, error) {
	panic("OAuthNativeExchange not stubbed")
}

func (s *stubAuthClient) Me(context.Context, string) (auth.User, error) {
	panic("Me not stubbed")
}

func (s *stubAuthClient) ClaimUsername(context.Context, string, string) (auth.User, error) {
	panic("ClaimUsername not stubbed")
}

func (s *stubAuthClient) CreateAPIKey(ctx context.Context, jwt string, req auth.CreateAPIKeyRequest) (auth.CreatedAPIKey, error) {
	if s.createAPIKey == nil { // pragma: allowlist secret
		panic("CreateAPIKey not stubbed")
	}

	return s.createAPIKey(ctx, jwt, req)
}

func (s *stubAuthClient) ListAPIKeys(ctx context.Context, jwt string) ([]auth.APIKey, error) {
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

// stubStore returns a WithCredStore option that always yields store.
func stubStore(store credstore.Store) AuthOption {
	return WithCredStore(func() (credstore.Store, error) { return store, nil })
}

// stubClient returns a WithAuthClient option that always yields client,
// ignoring the addr argument.
func stubClient(client auth.Client) AuthOption {
	return WithAuthClient(func(string) auth.Client { return client })
}

func TestNewAuthCmd_RegistersExpectedSubcommands(t *testing.T) {
	cmd := NewAuthCmd()

	names := make(map[string]bool)
	for _, sub := range cmd.Commands() {
		names[sub.Name()] = true
	}

	require.True(t, names["login"], "expected login subcommand")
	require.True(t, names["logout"], "expected logout subcommand")
	require.True(t, names["providers"], "expected providers subcommand")
	require.True(t, names["status"], "expected status subcommand")
}

func TestAuthLogin_RequiresAddr(t *testing.T) {
	testSetup(t)

	cmd := NewAuthCmd(stubStore(&memStore{}))
	cmd.SetArgs([]string{"login", "github"})

	var out bytes.Buffer
	cmd.SetOut(&out)
	cmd.SetErr(&out)

	err := cmd.ExecuteContext(context.Background())
	require.Error(t, err)
	require.Contains(t, err.Error(), envVarAddr)
}

func TestAuthLogout_ClearsStoredCredentials(t *testing.T) {
	testSetup(t)

	store := &memStore{}
	require.NoError(t, store.Save(credstore.Credentials{SessionJWT: "j", Username: "alice"}))

	cmd := NewAuthCmd(stubStore(store))
	cmd.SetArgs([]string{"logout"})

	var out bytes.Buffer
	cmd.SetOut(&out)

	require.NoError(t, cmd.ExecuteContext(context.Background()))
	require.Contains(t, out.String(), "Signed out")

	_, err := store.Load()
	require.ErrorIs(t, err, credstore.ErrNotFound)
}

func TestAuthStatus_NotSignedInReturnsErrNotFound(t *testing.T) {
	testSetup(t)

	cmd := NewAuthCmd(stubStore(&memStore{}))
	cmd.SetArgs([]string{"status"})

	var out bytes.Buffer
	cmd.SetOut(&out)

	err := cmd.ExecuteContext(context.Background())
	require.ErrorIs(t, err, credstore.ErrNotFound)
	require.Contains(t, out.String(), "Not signed in")
}

func TestAuthStatus_SignedInRendersIdentity(t *testing.T) {
	testSetup(t)
	setFlag(t, &flagAddr, "https://platform.example.com")

	store := &memStore{}
	require.NoError(t, store.Save(credstore.Credentials{SessionJWT: "j", Username: "alice"}))

	cmd := NewAuthCmd(stubStore(store))
	cmd.SetArgs([]string{"status"})

	var out bytes.Buffer
	cmd.SetOut(&out)

	require.NoError(t, cmd.ExecuteContext(context.Background()))
	require.Contains(t, out.String(), "https://platform.example.com")
	require.Contains(t, out.String(), "alice")
}

func TestAuthProviders_RequiresAddr(t *testing.T) {
	testSetup(t)

	cmd := NewAuthCmd()
	cmd.SetArgs([]string{"providers"})

	var out bytes.Buffer
	cmd.SetOut(&out)
	cmd.SetErr(&out)

	err := cmd.ExecuteContext(context.Background())
	require.Error(t, err)
	require.Contains(t, err.Error(), envVarAddr)
}

func TestAuthProviders_ListsEnabledOnly_AlphabeticallySorted(t *testing.T) {
	testSetup(t)
	setFlag(t, &flagAddr, "https://platform.example.com")

	client := &stubAuthClient{
		oauthProviders: func(context.Context) ([]auth.Provider, error) {
			return []auth.Provider{
				{Name: "google", DisplayName: "Google", Enabled: true},
				{Name: "azure", DisplayName: "Azure", Enabled: false},
				{Name: "github", DisplayName: "GitHub", Enabled: true},
			}, nil
		},
	}

	cmd := NewAuthCmd(stubClient(client))
	cmd.SetArgs([]string{"providers"})

	var out bytes.Buffer
	cmd.SetOut(&out)

	require.NoError(t, cmd.ExecuteContext(context.Background()))

	// One machine-readable name per line, ready to pipe straight into
	// `cq auth login` or downstream tooling.
	require.Equal(t, "github\ngoogle\n", out.String())
}

func TestAuthProviders_PropagatesPlatformError(t *testing.T) {
	testSetup(t)
	setFlag(t, &flagAddr, "https://platform.example.com")

	want := errors.New("upstream boom")

	client := &stubAuthClient{
		oauthProviders: func(context.Context) ([]auth.Provider, error) {
			return nil, want
		},
	}

	cmd := NewAuthCmd(stubClient(client))
	cmd.SetArgs([]string{"providers"})

	var out bytes.Buffer
	cmd.SetOut(&out)
	cmd.SetErr(&out)

	err := cmd.ExecuteContext(context.Background())
	require.ErrorIs(t, err, want)
}

func TestAuthLogin_MissingProviderArg_RejectsBeforeRunE(t *testing.T) {
	testSetup(t)
	setFlag(t, &flagAddr, "https://platform.example.com")

	cmd := NewAuthCmd(stubStore(&memStore{}))
	cmd.SetArgs([]string{"login"})

	var out bytes.Buffer
	cmd.SetOut(&out)
	cmd.SetErr(&out)

	err := cmd.ExecuteContext(context.Background())
	require.Error(t, err)
	require.Contains(t, err.Error(), "provider required")
	require.Contains(t, err.Error(), `"cq auth providers"`)
}

func TestAuthLogin_WhitespaceProviderArg_RejectsBeforeRunE(t *testing.T) {
	testSetup(t)
	setFlag(t, &flagAddr, "https://platform.example.com")

	cmd := NewAuthCmd(stubStore(&memStore{}))
	cmd.SetArgs([]string{"login", "    "})

	var out bytes.Buffer
	cmd.SetOut(&out)
	cmd.SetErr(&out)

	err := cmd.ExecuteContext(context.Background())
	require.Error(t, err)
	require.Contains(t, err.Error(), "provider required")
}
