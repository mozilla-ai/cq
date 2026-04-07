package cq

import "github.com/mozilla-ai/cq/sdk/go/internal/protocol"

// Prompt returns the canonical cq agent protocol prompt.
// This can be called without creating a Client.
func Prompt() string {
	return protocol.Prompt()
}
