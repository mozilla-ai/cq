// Package hook handles coding-agent lifecycle events dispatched to the cq
// binary by a host's hook configuration.
//
// NOTE: handlers report errors to their caller, but the cq _hook command
// swallows them and exits 0, so a hook never blocks the agent on internal
// failure. Payload parsing degrades to an empty payload rather than erroring.
package hook
