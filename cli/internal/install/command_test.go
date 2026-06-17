package install

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestTransformCommandStripsNameAddsAgent(t *testing.T) {
	source := "---\nname: cq:reflect\ndescription: Mine the session.\n---\n\n# Reflect\n\nBody.\n"
	got := transformCommand(source)
	require.NotContains(t, got, "name:")
	require.Contains(t, got, "agent: build\n")
	require.Contains(t, got, "description: Mine the session.\n")
	require.Contains(t, got, "# Reflect")
}

func TestTransformCommandPreservesBodyAndDescription(t *testing.T) {
	source := "---\nname: cq:status\ndescription: Show stats.\n---\n\n# Status\n\nBody content.\n"
	got := transformCommand(source)
	require.Equal(t, "---\ndescription: Show stats.\nagent: build\n---\n\n# Status\n\nBody content.\n", got)
}

func TestTransformCommandReturnsUnchangedWithoutFrontmatter(t *testing.T) {
	source := "# No Frontmatter\n\nJust content.\n"
	require.Equal(t, source, transformCommand(source))
}

func TestTransformCommandReturnsUnchangedWithUnclosedFrontmatter(t *testing.T) {
	source := "---\nname: broken\ndescription: oops\n"
	require.Equal(t, source, transformCommand(source))
}

func TestTransformCommandHandlesNoNameLine(t *testing.T) {
	source := "---\ndescription: No name field.\n---\n\nBody.\n"
	got := transformCommand(source)
	require.Equal(t, "---\ndescription: No name field.\nagent: build\n---\n\nBody.\n", got)
}

func TestTransformCommandHandlesCRLF(t *testing.T) {
	source := "---\r\nname: cq:reflect\r\ndescription: Mine the session.\r\n---\r\n\r\n# Reflect\r\n"
	got := transformCommand(source)
	require.NotContains(t, got, "name:")
	require.Contains(t, got, "agent: build\n")
	require.Contains(t, got, "description: Mine the session.")
}

func TestTransformCommandEmptyInput(t *testing.T) {
	require.Equal(t, "", transformCommand(""))
}
