package cmd

import (
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/mozilla-ai/cq/cli/internal/install"
)

func TestTargetsSetAccumulatesAndDedupes(t *testing.T) {
	sel := targets{}
	require.NoError(t, sel.Set("cursor"))
	require.NoError(t, sel.Set("windsurf"))
	require.NoError(t, sel.Set("cursor"))
	require.Equal(t, install.Targets{install.TargetCursor, install.TargetWindsurf}, sel.names())
}

func TestTargetsSetSplitsCommasAndTrims(t *testing.T) {
	sel := targets{}
	require.NoError(t, sel.Set(" cursor , windsurf "))
	require.Equal(t, install.Targets{install.TargetCursor, install.TargetWindsurf}, sel.names())
}

func TestTargetsSetGarbageInputIsNoOp(t *testing.T) {
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
			sel := targets{}
			require.NoError(t, sel.Set(tc.input))
			require.Empty(t, sel)
		})
	}
}

func TestTargetsSetRejectsUnknown(t *testing.T) {
	sel := targets{}
	err := sel.Set("emacs")
	require.Error(t, err)
	require.Contains(t, err.Error(), "unknown target emacs")
	require.Contains(t, err.Error(), "cursor")
}

func TestTargetsStringAndType(t *testing.T) {
	sel := targets{}
	require.NoError(t, sel.Set("windsurf,cursor"))
	require.Equal(t, "target", sel.Type())
	require.Equal(t, "cursor, windsurf", sel.String())
}
