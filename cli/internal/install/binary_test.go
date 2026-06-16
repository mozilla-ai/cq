package install

import (
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestBinaryPathHonorsOverride(t *testing.T) {
	abs := filepath.Join(t.TempDir(), "cq")
	t.Setenv(binaryOverrideEnv, abs)
	got, err := BinaryPath()
	require.NoError(t, err)
	require.Equal(t, abs, got)
}

func TestBinaryPathIsAbsolute(t *testing.T) {
	t.Setenv(binaryOverrideEnv, "")
	got, err := BinaryPath()
	require.NoError(t, err)
	require.True(t, filepath.IsAbs(got))
}

func TestBinaryPathRejectsRelativeOverride(t *testing.T) {
	t.Setenv(binaryOverrideEnv, "relative/cq")
	_, err := BinaryPath()
	require.Error(t, err)
}
