//go:build !darwin && !windows

package auth

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestBrowserCommand_Unix(t *testing.T) {
	name, args := browserCommand("https://example.com")
	require.Equal(t, "xdg-open", name)
	require.Equal(t, []string{"https://example.com"}, args)
}
