// Package protocol provides the embedded cq agent protocol prompt.
package protocol

import _ "embed"

//go:embed skill.md
var skill string

// Prompt returns the full agent protocol prompt.
func Prompt() string {
	return skill
}
