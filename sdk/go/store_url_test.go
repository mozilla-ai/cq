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

	t.Run("no slashes after the scheme", func(t *testing.T) {
		t.Parallel()

		dbPath := filepath.Join(dir, "opaque.db")

		storeFromURLCreatesDBPath(t, "sqlite:"+filepath.ToSlash(dbPath), dbPath)
	})
}

// TestStoreFromURLKeepsRelativePath pins the sqlite:<path> form to the working
// directory. Only a relative path reaches the URL's opaque part on every
// platform, because url.Parse puts a path with a leading separator in Path.
func TestStoreFromURLKeepsRelativePath(t *testing.T) {
	t.Chdir(t.TempDir())

	storeFromURLCreatesDBPath(t, "sqlite:relative.db", "relative.db")
}

// TestStoreFromURLRejectsAuthority pins that a sqlite: URL carrying an
// authority fails instead of opening what remains of the URL as a path.
//
// SQLite has no host, so an authority almost always means the URL is one slash
// short, and the store would otherwise open a file the caller never named.
func TestStoreFromURLRejectsAuthority(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name      string
		authority string
	}{
		{name: "host", authority: "ghost-host"},
		{name: "localhost", authority: "localhost"},
		{name: "Windows drive letter", authority: "C:"},
		{name: "user info without a host", authority: "user@"},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			dbPath := filepath.Join(t.TempDir(), "wanted.db")
			connURL := "sqlite://" + tc.authority + "/" + strings.TrimPrefix(filepath.ToSlash(dbPath), "/")

			s, err := cq.StoreFromURL(connURL)
			if s != nil {
				t.Cleanup(func() { _ = s.Close() })
			}

			require.ErrorContains(t, err, "sqlite:///")
			require.NoFileExists(t, dbPath)
		})
	}
}

// sqliteURL builds the documented "sqlite:///<path>" form from an absolute
// path, keeping the separators the caller wrote so that each subtest exercises
// the form it names.
//
// NOTE: the "sqlite:///" prefix already supplies the separator that introduces
// the URL path, so a leading separator on dbPath must come off or the URL gains
// an empty first path segment.
func sqliteURL(dbPath string) string {
	return "sqlite:///" + strings.TrimPrefix(dbPath, string(filepath.Separator))
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
