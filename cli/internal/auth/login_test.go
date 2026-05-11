package auth

import (
	"bytes"
	"context"
	"errors"
	"net/http"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/mozilla-ai/cq/cli/internal/credstore"
)

// memStore is an in-memory credstore.Store used to assert what Login
// persists. The Mutex keeps Save/Load safe against any incidental
// concurrent access from the test driver.
type memStore struct {
	sync.Mutex
	creds   credstore.Credentials
	hasData bool
}

func newMemStore() *memStore { return &memStore{} }

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

// driveCallback returns an OpenBrowser stub that completes the loopback
// callback with the supplied query string (e.g. "exchange_code=abc").
// The stub records the authorization URL it was called with into got.
func driveCallback(t *testing.T, got *string, mu *sync.Mutex, query string) func(string) error {
	t.Helper()

	return func(authURL string) error {
		mu.Lock()
		*got = authURL
		mu.Unlock()

		go func() {
			// The redirect_uri is captured by the Client stub; read it
			// after a brief wait so OAuthNativeStart has returned.
			time.Sleep(10 * time.Millisecond)

			redirectURI := readRedirectURI(t)

			resp, err := http.Get(redirectURI + "?" + query)
			if err == nil {
				_ = resp.Body.Close()
			}
		}()

		return nil
	}
}

// redirectURIRecorder lets the Client stub stash the redirect_uri it
// receives so the OpenBrowser stub can later issue an HTTP callback to
// the loopback listener.
type redirectURIRecorder struct {
	sync.Mutex
	value string
	ready chan struct{}
}

func newRedirectURIRecorder() *redirectURIRecorder {
	return &redirectURIRecorder{ready: make(chan struct{})}
}

func (r *redirectURIRecorder) record(uri string) {
	r.Lock()
	r.value = uri
	r.Unlock()
	close(r.ready)
}

func (r *redirectURIRecorder) get() string {
	r.Lock()
	defer r.Unlock()

	return r.value
}

// activeRecorder is the per-test recorder shared between the Client
// stub and the OpenBrowser stub. Reset for each test that needs it.
var activeRecorder *redirectURIRecorder

func readRedirectURI(t *testing.T) string {
	t.Helper()

	select {
	case <-activeRecorder.ready:
		return activeRecorder.get()
	case <-time.After(2 * time.Second):
		t.Fatal("redirect URI not recorded by OAuthNativeStart")

		return ""
	}
}

func TestLogin_HappyPath_StoresJWTAndUsername(t *testing.T) {
	activeRecorder = newRedirectURIRecorder()

	client := &stubAuthClient{
		oauthNativeStart: func(_ context.Context, req NativeStartRequest) (string, error) {
			activeRecorder.record(req.RedirectURI)

			return "https://provider.example/auth", nil
		},
		oauthNativeExchange: func(_ context.Context, req NativeExchangeRequest) (string, error) {
			require.Equal(t, "exchange-abc", req.ExchangeCode)
			require.NotEmpty(t, req.CodeVerifier)

			return "session-jwt", nil
		},
		me: func(_ context.Context, jwt string) (User, error) {
			require.Equal(t, "session-jwt", jwt)

			return User{Username: "alice", OAuthProvider: "github"}, nil
		},
	}

	store := newMemStore()
	out := &bytes.Buffer{}

	var (
		seenAuthURL string
		mu          sync.Mutex
	)

	err := Login(context.Background(), LoginConfig{
		Provider: "github",
		Client:   client,
		Store:    store,
		// "\n" satisfies the "press Enter to open browser" prompt.
		In:          strings.NewReader("\n"),
		Out:         out,
		OpenBrowser: driveCallback(t, &seenAuthURL, &mu, "exchange_code=exchange-abc"),
	})
	require.NoError(t, err)

	mu.Lock()
	require.Equal(t, "https://provider.example/auth", seenAuthURL)
	mu.Unlock()

	saved, err := store.Load()
	require.NoError(t, err)
	require.Equal(t, "session-jwt", saved.SessionJWT)
	require.Equal(t, "alice", saved.Username)

	require.Contains(t, out.String(), "Signed in as alice")
}

func TestLogin_NewUser_RunsOnboardingThenStores(t *testing.T) {
	activeRecorder = newRedirectURIRecorder()

	client := &stubAuthClient{
		oauthNativeStart: func(_ context.Context, req NativeStartRequest) (string, error) {
			activeRecorder.record(req.RedirectURI)

			return "https://provider.example/auth", nil
		},
		oauthNativeExchange: func(context.Context, NativeExchangeRequest) (string, error) {
			return "session-jwt", nil
		},
		me: func(context.Context, string) (User, error) {
			return User{Username: ""}, nil
		},
		claimUsername: func(_ context.Context, _, username string) (User, error) {
			require.Equal(t, "newbie", username)

			return User{Username: "newbie"}, nil
		},
	}

	store := newMemStore()
	out := &bytes.Buffer{}

	err := Login(context.Background(), LoginConfig{
		Provider: "github",
		Client:   client,
		Store:    store,
		// First "\n" is the press-Enter prompt; "newbie\n" is the
		// username read by the onboarding loop.
		In:          strings.NewReader("\nnewbie\n"),
		Out:         out,
		OpenBrowser: driveCallback(t, new(string), new(sync.Mutex), "exchange_code=abc"),
	})
	require.NoError(t, err)

	saved, err := store.Load()
	require.NoError(t, err)
	require.Equal(t, "newbie", saved.Username)
}

func TestLogin_EmptyProviderReturnsErrProviderRequired(t *testing.T) {
	// stubAuthClient leaves all methods nil, so any platform call would
	// panic. The assertion is that Login never reaches one.
	client := &stubAuthClient{}

	err := Login(context.Background(), LoginConfig{
		Client: client,
		Store:  newMemStore(),
		In:     strings.NewReader(""),
		Out:    &bytes.Buffer{},
	})
	require.ErrorIs(t, err, ErrProviderRequired)
}

func TestLogin_ExchangeFailureDoesNotPersist(t *testing.T) {
	activeRecorder = newRedirectURIRecorder()

	client := &stubAuthClient{
		oauthNativeStart: func(_ context.Context, req NativeStartRequest) (string, error) {
			activeRecorder.record(req.RedirectURI)

			return "https://provider.example/auth", nil
		},
		oauthNativeExchange: func(context.Context, NativeExchangeRequest) (string, error) {
			return "", ErrInvalidGrant
		},
	}

	store := newMemStore()

	err := Login(context.Background(), LoginConfig{
		Provider:    "github",
		Client:      client,
		Store:       store,
		In:          strings.NewReader("\n"),
		Out:         &bytes.Buffer{},
		OpenBrowser: driveCallback(t, new(string), new(sync.Mutex), "exchange_code=abc"),
	})
	require.ErrorIs(t, err, ErrInvalidGrant)

	_, loadErr := store.Load()
	require.ErrorIs(t, loadErr, credstore.ErrNotFound)
}

func TestLogin_ListenerTimeoutReturnsHelpfulError(t *testing.T) {
	activeRecorder = newRedirectURIRecorder()

	client := &stubAuthClient{
		oauthNativeStart: func(_ context.Context, req NativeStartRequest) (string, error) {
			activeRecorder.record(req.RedirectURI)

			return "https://provider.example/auth", nil
		},
	}

	noBrowser := func(string) error { return errors.New("not running browser in test") }

	err := Login(context.Background(), LoginConfig{
		Provider:    "github",
		Client:      client,
		Store:       newMemStore(),
		In:          strings.NewReader("\n"),
		Out:         &bytes.Buffer{},
		OpenBrowser: noBrowser,
		Timeout:     50 * time.Millisecond,
	})
	require.Error(t, err)
	require.Contains(t, err.Error(), "didn't complete in time")
}

func TestLogin_BrowserFailurePrintsManualURL(t *testing.T) {
	activeRecorder = newRedirectURIRecorder()

	authURL := "https://provider.example/auth?state=xyz"

	client := &stubAuthClient{
		oauthNativeStart: func(_ context.Context, req NativeStartRequest) (string, error) {
			activeRecorder.record(req.RedirectURI)

			return authURL, nil
		},
		oauthNativeExchange: func(context.Context, NativeExchangeRequest) (string, error) {
			return "session-jwt", nil
		},
		me: func(context.Context, string) (User, error) {
			return User{Username: "alice"}, nil
		},
	}

	out := &bytes.Buffer{}

	failingBrowser := func(string) error {
		go func() {
			time.Sleep(10 * time.Millisecond)

			redirectURI := readRedirectURI(t)

			resp, err := http.Get(redirectURI + "?exchange_code=abc")
			if err == nil {
				_ = resp.Body.Close()
			}
		}()

		return errors.New("xdg-open: not found")
	}

	err := Login(context.Background(), LoginConfig{
		Provider:    "github",
		Client:      client,
		Store:       newMemStore(),
		In:          strings.NewReader("\n"),
		Out:         out,
		OpenBrowser: failingBrowser,
	})
	require.NoError(t, err)
	// The URL should have been printed before the prompt, so the user
	// can paste it manually if the launcher fails.
	require.Contains(t, out.String(), authURL)
	require.Contains(t, out.String(), "Couldn't open browser automatically")
}

func TestLogin_CancelledBeforeBrowserPromptReturnsError(t *testing.T) {
	activeRecorder = newRedirectURIRecorder()

	client := &stubAuthClient{
		oauthNativeStart: func(_ context.Context, req NativeStartRequest) (string, error) {
			activeRecorder.record(req.RedirectURI)

			return "https://provider.example/auth", nil
		},
	}

	err := Login(context.Background(), LoginConfig{
		Provider: "github",
		Client:   client,
		Store:    newMemStore(),
		// Empty input: EOF before the user presses Enter.
		In:  strings.NewReader(""),
		Out: &bytes.Buffer{},
		OpenBrowser: func(string) error {
			t.Fatal("OpenBrowser should not be called when the user cancels at the prompt")

			return nil
		},
	})
	require.Error(t, err)
	require.Contains(t, err.Error(), "cancelled")
}
