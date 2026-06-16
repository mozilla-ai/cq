package prompts

import _ "embed"

//go:embed reflect.md
var reflect string

//go:embed SKILL.md
var skill string

//go:embed status.md
var status string

// Reflect returns the /cq:reflect slash-command prompt.
func Reflect() string {
	return reflect
}

// Skill returns the full cq agent skill prompt.
func Skill() string {
	return skill
}

// Status returns the /cq:status slash-command prompt.
func Status() string {
	return status
}
