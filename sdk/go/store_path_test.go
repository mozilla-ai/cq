package cq

import (
	"net/url"
	"testing"

	"github.com/stretchr/testify/require"
)

// TestDropWindowsDriveSeparator exercises the drive-letter rule on any host.
//
// The rule applies on Windows, where it runs on a machine the project owns no
// other coverage for, so it is kept as a pure function that a Linux or macOS
// test can call directly.
func TestDropWindowsDriveSeparator(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name string
		path string
		want string
	}{
		{
			name: "drive letter after the separator",
			path: "/C:/data/local.db",
			want: "C:/data/local.db",
		},
		{
			name: "lower case drive letter",
			path: "/c:/data/local.db",
			want: "c:/data/local.db",
		},
		{
			name: "backslash separator is dropped too",
			path: `/C:\data\local.db`,
			want: `C:\data\local.db`,
		},
		{
			name: "a path that is not drive rooted is untouched",
			path: "/data/local.db",
			want: "/data/local.db",
		},
		{
			name: "a UNC prefix keeps both separators",
			path: `//host/share/local.db`,
			want: `//host/share/local.db`,
		},
		{
			name: "a Windows UNC prefix with backslashes keeps both separators",
			path: `\\host\share\local.db`,
			want: `\\host\share\local.db`,
		},
		{
			name: "a digit is not a drive letter",
			path: "/1:/data/local.db",
			want: "/1:/data/local.db",
		},
		{
			name: "shorter than a drive prefix",
			path: "/C",
			want: "/C",
		},
		{
			name: "exactly the drive prefix without a trailing segment",
			path: "/C:",
			want: "C:",
		},
		{
			name: "empty path",
			path: "",
			want: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			require.Equal(t, tt.want, dropWindowsDriveSeparator(tt.path))
		})
	}
}

// TestSQLitePathFromURL pins which part of a parsed sqlite: URL becomes the
// store path, for both accepted forms.
func TestSQLitePathFromURL(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name string
		url  string
		want string
	}{
		{
			name: "opaque form is used as it is",
			url:  "sqlite:/data/local.db",
			want: "/data/local.db",
		},
		{
			name: "host-less form keeps its path",
			url:  "sqlite:///data/local.db",
			want: "/data/local.db",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			parsed, err := url.Parse(tt.url)
			require.NoError(t, err)

			require.Equal(t, tt.want, sqlitePathFromURL(parsed))
		})
	}
}
