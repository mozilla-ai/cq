// Package prompts provides the canonical cq agent prompts embedded from
// the plugin authoring sources. Each prompt is synced into this package via
// `make sync-prompts` so SDK consumers can surface the same text that the
// Claude Code and OpenCode slash commands use.
package prompts

import _ "embed"

//go:embed reflect.md
var reflect string

//go:embed SKILL.md
var skill string

// Reflect returns the /cq:reflect slash-command prompt.
func Reflect() string {
	return reflect
}

// Skill returns the full cq agent skill prompt.
func Skill() string {
	return skill
}
