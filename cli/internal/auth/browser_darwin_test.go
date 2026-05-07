package auth

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestBrowserCommand_Darwin(t *testing.T) {
	name, args := browserCommand("https://example.com")
	require.Equal(t, "open", name)
	require.Equal(t, []string{"https://example.com"}, args)
}
