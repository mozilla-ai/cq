package install

import (
	"maps"
	"slices"
	"strings"
)

const (
	// TargetClaude is Claude Code via the plugin marketplace.
	TargetClaude Target = "claude"

	// TargetCursor is the Cursor editor.
	TargetCursor Target = "cursor"

	// TargetOpenCode is the OpenCode editor.
	TargetOpenCode Target = "opencode"

	// TargetPi is the Pi coding agent.
	TargetPi Target = "pi"

	// TargetWindsurf is the Windsurf editor.
	TargetWindsurf Target = "windsurf"
)

// hosts is every supported install adapter, keyed by target.
//
// It is the single source of truth for the targets cq install accepts; adding
// an entry extends ValidTarget, AllowedTargets, and SelectHosts.
var hosts = map[Target]Host{
	TargetClaude:   claudeHost{},
	TargetCursor:   cursorHost{},
	TargetOpenCode: opencodeHost{},
	TargetPi:       piHost{},
	TargetWindsurf: windsurfHost{},
}

// Target identifies a supported coding-agent host.
type Target string

// Targets is a set of targets that renders as a sorted, comma-separated list.
type Targets []Target

// String renders the targets as a comma-separated list.
func (ts Targets) String() string {
	parts := make([]string, len(ts))
	for i, t := range ts {
		parts[i] = string(t)
	}
	return strings.Join(parts, ", ")
}

// AllowedTargets returns the supported targets as a sorted display list.
//
// NOTE: use ValidTarget for membership checks — this allocates a slice and is
// intended for rendering help and error messages.
func AllowedTargets() Targets {
	return Targets(slices.Sorted(maps.Keys(hosts)))
}

// SelectHosts returns the adapters for the named targets in stable, sorted
// order, skipping any name not present in the hosts map.
func SelectHosts(names Targets) []Host {
	selected := make([]Host, 0, len(names))
	for _, name := range slices.Sorted(slices.Values(names)) {
		if h, ok := hosts[name]; ok {
			selected = append(selected, h)
		}
	}
	return selected
}

// ValidTarget reports whether name is a supported install target.
func ValidTarget(name Target) bool {
	_, ok := hosts[name]
	return ok
}
