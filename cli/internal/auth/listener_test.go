package auth

import (
	"context"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestListener_URL_BindsLocalhostOnly(t *testing.T) {
	l, err := startListener()
	require.NoError(t, err)
	t.Cleanup(func() { _ = l.Close() })

	u, err := url.Parse(l.URL())
	require.NoError(t, err)

	host, _, err := net.SplitHostPort(u.Host)
	require.NoError(t, err)

	ip := net.ParseIP(host)
	require.NotNil(t, ip, "expected an IP address, got %s", host)
	require.True(t, ip.IsLoopback(), "expected loopback address, got %s", ip)
	require.Equal(t, "/cb", u.Path)
}

func TestListener_Wait_ReturnsExchangeCodeOnCallback(t *testing.T) {
	l, err := startListener()
	require.NoError(t, err)
	t.Cleanup(func() { _ = l.Close() })

	go callback(t, l.URL()+"?exchange_code=abc123")

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	got, err := l.Wait(ctx)
	require.NoError(t, err)
	require.Equal(t, "abc123", got)
}

func TestListener_Wait_PropagatesProviderError(t *testing.T) {
	l, err := startListener()
	require.NoError(t, err)
	t.Cleanup(func() { _ = l.Close() })

	go callback(t, l.URL()+"?error=access_denied&error_description=user+cancelled")

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	_, err = l.Wait(ctx)
	require.Error(t, err)
	require.ErrorContains(t, err, "access_denied")
	require.ErrorContains(t, err, "user cancelled")
}

func TestListener_Wait_PropagatesProviderErrorWithoutDescription(t *testing.T) {
	l, err := startListener()
	require.NoError(t, err)
	t.Cleanup(func() { _ = l.Close() })

	go callback(t, l.URL()+"?error=server_error")

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	_, err = l.Wait(ctx)
	require.Error(t, err)
	require.ErrorContains(t, err, "server_error")
}

func TestListener_Wait_RejectsCallbackMissingExchangeCodeAndError(t *testing.T) {
	l, err := startListener()
	require.NoError(t, err)
	t.Cleanup(func() { _ = l.Close() })

	go callback(t, l.URL())

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	_, err = l.Wait(ctx)
	require.Error(t, err)
}

func TestListener_NonCallbackPathReturns404(t *testing.T) {
	l, err := startListener()
	require.NoError(t, err)
	t.Cleanup(func() { _ = l.Close() })

	base := strings.TrimSuffix(l.URL(), "/cb")
	resp, err := http.Get(base + "/somewhere-else")
	require.NoError(t, err)
	defer func() { _ = resp.Body.Close() }()

	require.Equal(t, http.StatusNotFound, resp.StatusCode)
}

func TestListener_Wait_IgnoresSubsequentCallbacks(t *testing.T) {
	l, err := startListener()
	require.NoError(t, err)
	t.Cleanup(func() { _ = l.Close() })

	go callback(t, l.URL()+"?exchange_code=first")

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	got, err := l.Wait(ctx)
	require.NoError(t, err)
	require.Equal(t, "first", got)

	// Subsequent valid callbacks must not affect the captured value or
	// hang the listener.
	resp, err := http.Get(l.URL() + "?exchange_code=second")
	require.NoError(t, err)
	defer func() { _ = resp.Body.Close() }()
}

func TestListener_SuccessCallback_RendersSuccessPage(t *testing.T) {
	l, err := startListener()
	require.NoError(t, err)
	t.Cleanup(func() { _ = l.Close() })

	resp, err := http.Get(l.URL() + "?exchange_code=abc")
	require.NoError(t, err)
	defer func() { _ = resp.Body.Close() }()

	require.Equal(t, http.StatusOK, resp.StatusCode)

	body, err := io.ReadAll(resp.Body)
	require.NoError(t, err)
	require.Contains(t, string(body), "signed in")
}

func TestListener_ErrorCallback_RendersErrorPageNotSuccessPage(t *testing.T) {
	l, err := startListener()
	require.NoError(t, err)
	t.Cleanup(func() { _ = l.Close() })

	resp, err := http.Get(l.URL() + "?error=access_denied&error_description=user+cancelled")
	require.NoError(t, err)
	defer func() { _ = resp.Body.Close() }()

	require.GreaterOrEqual(t, resp.StatusCode, http.StatusBadRequest,
		"error callback must not respond with a 2xx status")

	body, err := io.ReadAll(resp.Body)
	require.NoError(t, err)
	require.NotContains(t, string(body), "You're signed in",
		"error callback must not render the success page")
	require.Contains(t, string(body), "didn't complete")

	// The CLI side still receives the parsed error.
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	_, err = l.Wait(ctx)
	require.Error(t, err)
	require.ErrorContains(t, err, "access_denied")
}

func TestListener_Wait_HonoursContextCancellation(t *testing.T) {
	l, err := startListener()
	require.NoError(t, err)
	t.Cleanup(func() { _ = l.Close() })

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	_, err = l.Wait(ctx)
	require.ErrorIs(t, err, context.DeadlineExceeded)
}

// callback issues a GET against u and asserts the response body succeeds.
// It runs in a goroutine to drive the listener under test.
func callback(t *testing.T, u string) {
	t.Helper()

	resp, err := http.Get(u)
	if err != nil {
		t.Logf("callback request failed: %v", err)

		return
	}
	defer func() { _ = resp.Body.Close() }()
}
