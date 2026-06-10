package discovery

import (
	"io"
	"log/slog"
	"net/http"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestDefaultOptionsValues(t *testing.T) {
	t.Parallel()

	o := defaultOptions()
	require.Empty(t, o.cacheDir)
	require.NotNil(t, o.httpClient)
	require.Equal(t, 5*time.Second, o.httpClient.Timeout)
	require.NotNil(t, o.logger)
}

func TestNewSkipsNilOption(t *testing.T) {
	t.Parallel()

	// A nil Option in the variadic should be tolerated, not cause a
	// panic or fail option application. This keeps composition
	// patterns like `append(opts, conditional)` safe even when the
	// conditional yields nil.
	r, err := New(nil)
	require.NoError(t, err)
	require.NotNil(t, r)
}

func TestWithCacheDirAcceptsAbsolutePath(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	require.True(t, filepath.IsAbs(dir))

	var o options
	require.NoError(t, WithCacheDir(dir)(&o))
	require.Equal(t, dir, o.cacheDir)
}

func TestWithCacheDirRejectsEmpty(t *testing.T) {
	t.Parallel()

	var o options
	err := WithCacheDir("")(&o)
	require.Error(t, err)
	require.Contains(t, err.Error(), "empty")
}

func TestWithCacheDirRejectsRelativePath(t *testing.T) {
	t.Parallel()

	var o options
	err := WithCacheDir("relative/path")(&o)
	require.Error(t, err)
	require.Contains(t, err.Error(), "absolute")
}

func TestWithCacheDirRejectsWhitespace(t *testing.T) {
	t.Parallel()

	var o options
	err := WithCacheDir("   \t  ")(&o)
	require.Error(t, err)
	require.Contains(t, err.Error(), "empty")
}

func TestWithCacheDirTrimsSurroundingWhitespace(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	var o options
	require.NoError(t, WithCacheDir("  "+dir+"  ")(&o))
	require.Equal(t, dir, o.cacheDir)
}

func TestWithHTTPClientRejectsNil(t *testing.T) {
	t.Parallel()

	var o options
	err := WithHTTPClient(nil)(&o)
	require.Error(t, err)
	require.Contains(t, err.Error(), "nil")
}

func TestWithHTTPClientStoresProvidedClient(t *testing.T) {
	t.Parallel()

	client := &http.Client{Timeout: 42 * time.Second}
	var o options
	require.NoError(t, WithHTTPClient(client)(&o))
	require.Same(t, client, o.httpClient)
}

func TestWithLoggerRejectsNil(t *testing.T) {
	t.Parallel()

	var o options
	err := WithLogger(nil)(&o)
	require.Error(t, err)
	require.Contains(t, err.Error(), "nil")
}

func TestWithLoggerStoresProvidedLogger(t *testing.T) {
	t.Parallel()

	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	var o options
	require.NoError(t, WithLogger(logger)(&o))
	require.Same(t, logger, o.logger)
}
