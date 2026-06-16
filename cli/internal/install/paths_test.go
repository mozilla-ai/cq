package install

import (
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestSharedSkillsDir(t *testing.T) {
	got := SharedSkillsDir("/home/dev")
	require.Equal(t, filepath.Join("/home/dev", ".agents", "skills"), got)
}

func TestWindsurfTarget(t *testing.T) {
	got := windsurfTarget("/home/dev")
	require.Equal(t, filepath.Join("/home/dev", ".codeium", "windsurf"), got)
}
