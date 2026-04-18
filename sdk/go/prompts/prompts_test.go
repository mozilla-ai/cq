package prompts

import (
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestSkillContainsSkillFrontmatter(t *testing.T) {
	body := Skill()
	require.NotEmpty(t, body)
	require.True(t, strings.HasPrefix(body, "---\n"), "skill prompt must start with frontmatter")
	require.Contains(t, body, "name: cq")
	require.Contains(t, body, "## Core Protocol")
}

func TestReflectContainsReflectFrontmatter(t *testing.T) {
	body := Reflect()
	require.NotEmpty(t, body)
	require.True(t, strings.HasPrefix(body, "---\n"), "reflect prompt must start with frontmatter")
	require.Contains(t, body, "name: cq:reflect")
	require.Contains(t, body, "### Step 1")
}

func TestSkillAndReflectAreDistinct(t *testing.T) {
	require.NotEqual(t, Skill(), Reflect())
}
