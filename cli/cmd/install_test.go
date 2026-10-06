package cmd

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/mozilla-ai/cq/cli/internal/install"
)

func TestTargetsSetAccumulatesAndDedupes(t *testing.T) {
	t.Parallel()

	sel := targets{}
	require.NoError(t, sel.Set("cursor"))
	require.NoError(t, sel.Set("devin-desktop"))
	require.NoError(t, sel.Set("cursor"))
	require.Equal(t, install.Targets{install.TargetCursor, install.TargetDevinDesktop}, sel.names())
}

func TestTargetsSetSplitsCommasAndTrims(t *testing.T) {
	t.Parallel()

	sel := targets{}
	require.NoError(t, sel.Set(" cursor , devin-desktop "))
	require.Equal(t, install.Targets{install.TargetCursor, install.TargetDevinDesktop}, sel.names())
}

func TestTargetsSetGarbageInputIsNoOp(t *testing.T) {
	t.Parallel()

	for _, tc := range []struct {
		name  string
		input string
	}{
		{"empty", ""},
		{"whitespace", "   "},
		{"bare commas", ", , , ,, ,,"},
		{"comma only", ","},
		{"tabs and newlines", " \t , \n "},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			sel := targets{}
			require.NoError(t, sel.Set(tc.input))
			require.Empty(t, sel)
		})
	}
}

func TestTargetsSetRejectsUnknown(t *testing.T) {
	t.Parallel()

	sel := targets{}
	err := sel.Set("emacs")
	require.Error(t, err)
	require.Contains(t, err.Error(), "unknown target emacs")
	require.Contains(t, err.Error(), "cursor")
}

func TestTargetsStringAndType(t *testing.T) {
	t.Parallel()

	sel := targets{}
	require.NoError(t, sel.Set("devin-desktop,cursor"))
	require.Equal(t, "target", sel.Type())
	require.Equal(t, "cursor, devin-desktop", sel.String())
}

func TestResolveProjectDir(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	file := filepath.Join(dir, "file.txt")
	require.NoError(t, os.WriteFile(file, nil, 0o600))

	tests := []struct {
		name    string
		path    string
		want    string
		wantErr string
	}{
		{name: "absolute directory", path: dir, want: dir},
		{name: "missing directory", path: filepath.Join(dir, "missing"), wantErr: "does not exist"},
		{name: "file instead of directory", path: file, wantErr: "is not a directory"},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			got, err := resolveProjectDir(tc.path)
			if tc.wantErr != "" {
				require.ErrorContains(t, err, tc.wantErr)
				require.ErrorContains(t, err, tc.path)
				return
			}

			require.NoError(t, err)
			require.Equal(t, tc.want, got)
		})
	}
}

func TestResolveProjectDirMakesRelativePathAbsolute(t *testing.T) {
	t.Parallel()

	wd, err := os.Getwd()
	require.NoError(t, err)

	got, err := resolveProjectDir(".")
	require.NoError(t, err)
	require.Equal(t, wd, got)
}
