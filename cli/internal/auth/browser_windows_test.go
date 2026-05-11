package auth

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestBrowserCommand_Windows(t *testing.T) {
	name, args := browserCommand("https://example.com")
	require.Equal(t, "rundll32", name)
	require.Equal(t, []string{"url.dll,FileProtocolHandler", "https://example.com"}, args)
}
