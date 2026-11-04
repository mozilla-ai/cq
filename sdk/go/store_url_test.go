package cq_test

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// TestStoreFromURLKeepsNativeAbsolutePath pins the documented
// "sqlite:///<path>" connection-string form to the path the caller actually
// wrote.
//
// The URL is built the way the docs and the conformance suite build it: the
// "sqlite:///" prefix followed by a native absolute path. The store must open
// that path and not a different one that merely happens to work.
func TestStoreFromURLKeepsNativeAbsolutePath(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()

	t.Run("native separators", func(t *testing.T) {
		t.Parallel()

		dbPath := filepath.Join(dir, "native.db")

		storeFromURLCreatesDBPath(t, sqliteURL(dbPath), dbPath)
	})

	t.Run("forward slashes", func(t *testing.T) {
		t.Parallel()

		dbPath := filepath.Join(dir, "slashed.db")

		storeFromURLCreatesDBPath(t, sqliteURL(filepath.ToSlash(dbPath)), dbPath)
	})
}

// sqliteURL builds the documented "sqlite:///<path>" form from a native
// absolute path.
//
// NOTE: the "sqlite:///" prefix already supplies the separator that introduces
// the URL path, so a leading separator on dbPath must come off or the URL gains
// an empty first path segment.
func sqliteURL(dbPath string) string {
	return "sqlite:///" + strings.TrimPrefix(filepath.ToSlash(dbPath), "/")
}

// storeFromURLCreatesDBPath asserts that connURL opens a working store at
// wantPath.
func storeFromURLCreatesDBPath(t *testing.T, connURL string, wantPath string) {
	t.Helper()

	s, err := cq.StoreFromURL(connURL)
	require.NoError(t, err)
	t.Cleanup(func() { _ = s.Close() })

	ku := cq.KnowledgeUnit{
		ID:      "ku_0000000000000000000000000000000a",
		Domains: []string{"api"},
	}
	require.NoError(t, s.Insert(context.Background(), ku))

	got, err := s.Unit(context.Background(), ku.ID)
	require.NoError(t, err)
	require.NotNil(t, got)

	// The store must be the file the caller asked for, not a different path
	// that merely happened to open.
	_, err = os.Stat(wantPath)
	require.NoError(t, err)
}
