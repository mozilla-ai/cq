package hook

import (
	"fmt"
	"io"
	"maps"
	"slices"
	"strings"
)

// HostCursor is the Cursor editor host.
const HostCursor Host = "cursor"

const (
	// ModeSessionStart fires when an agent session begins.
	ModeSessionStart Mode = "session-start"

	// ModePostToolUse fires after any tool call.
	ModePostToolUse Mode = "post-tool-use"

	// ModePostToolUseFailure fires after a failed tool call.
	ModePostToolUseFailure Mode = "post-tool-use-failure"

	// ModeStop fires when an agent turn ends.
	ModeStop Mode = "stop"
)

// handlers maps each host to its hook handler.
//
// It is the single source of truth for the hosts cq dispatches hooks for;
// adding an entry extends ValidHost, AllowedHosts, and Run.
var handlers = map[Host]handler{
	HostCursor: runCursor,
}

// modes is the set of canonical lifecycle modes.
//
// NOTE: use ValidMode for membership checks; AllowedModes for display.
var modes = map[Mode]struct{}{
	ModeSessionStart:       {},
	ModePostToolUse:        {},
	ModePostToolUseFailure: {},
	ModeStop:               {},
}

// handler runs one lifecycle invocation for a single host, reading the event
// payload from in and writing any user-facing output to out.
type handler func(inv Invocation, in io.Reader, out io.Writer) error

// Host names a coding-agent host with a registered hook handler. It implements
// pflag.Value so it can back a validated --host flag.
type Host string

// Hosts is a set of hosts that renders as a comma-separated list.
type Hosts []Host

// Invocation is a single lifecycle hook call: which host fired, which event,
// and where cross-event state is kept.
type Invocation struct {
	// Host is the coding-agent host whose hook fired.
	Host Host

	// Mode is the lifecycle event that fired.
	Mode Mode

	// StateDir is the directory holding cross-event hook state.
	StateDir string
}

// Mode is a canonical lifecycle event a host reports to cq. It implements
// pflag.Value so it can back a validated --mode flag.
type Mode string

// Modes is a set of modes that renders as a comma-separated list.
type Modes []Mode

// Set validates v against the registered hosts and records it.
func (h *Host) Set(v string) error {
	host := Host(strings.ToLower(strings.TrimSpace(v)))
	if _, ok := handlers[host]; !ok {
		return fmt.Errorf("unsupported hook host %s, supported: %s", v, AllowedHosts())
	}
	*h = host
	return nil
}

// String returns the host name.
func (h *Host) String() string { return string(*h) }

// Type names the value kind shown in help output.
func (h *Host) Type() string { return "host" }

// String renders the hosts as a comma-separated list.
func (hs Hosts) String() string {
	parts := make([]string, len(hs))
	for i, h := range hs {
		parts[i] = string(h)
	}
	return strings.Join(parts, ", ")
}

// Set validates v against the canonical modes and records it.
func (m *Mode) Set(v string) error {
	mode := Mode(strings.ToLower(strings.TrimSpace(v)))
	if !ValidMode(mode) {
		return fmt.Errorf("unsupported hook mode %s, supported: %s", v, AllowedModes())
	}
	*m = mode
	return nil
}

// String returns the mode name.
func (m *Mode) String() string { return string(*m) }

// Type names the value kind shown in help output.
func (m *Mode) Type() string { return "mode" }

// String renders the modes as a comma-separated list.
func (ms Modes) String() string {
	parts := make([]string, len(ms))
	for i, m := range ms {
		parts[i] = string(m)
	}
	return strings.Join(parts, ", ")
}

// AllowedHosts returns the registered hook hosts as a sorted display list.
//
// NOTE: use ValidHost for membership checks.
func AllowedHosts() Hosts {
	return Hosts(slices.Sorted(maps.Keys(handlers)))
}

// AllowedModes returns the canonical lifecycle modes as a sorted display list.
//
// NOTE: use ValidMode for membership checks.
func AllowedModes() Modes {
	return Modes(slices.Sorted(maps.Keys(modes)))
}

// Run dispatches one lifecycle invocation to its host's registered handler,
// reading the event payload from in and writing any user-facing output to out.
func Run(inv Invocation, in io.Reader, out io.Writer) error {
	h, ok := handlers[inv.Host]
	if !ok {
		return fmt.Errorf("unsupported hook host %s, supported: %s", inv.Host, AllowedHosts())
	}
	return h(inv, in, out)
}

// ValidHost reports whether name is a registered hook host.
func ValidHost(name Host) bool {
	_, ok := handlers[name]
	return ok
}

// ValidMode reports whether name is a canonical lifecycle mode.
func ValidMode(name Mode) bool {
	_, ok := modes[name]
	return ok
}
