package hook

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const (
	// maxPayloadBytes bounds hook stdin processing to avoid unbounded memory use.
	maxPayloadBytes = 1 << 20 // 1 MiB

	// maxSnippetLength bounds the captured command/error text surfaced at stop.
	maxSnippetLength = 200

	// stateTTL is how long a per-conversation failure record is retained
	// before session-start sweeps it.
	stateTTL = 24 * time.Hour

	// failureSuffix names a per-conversation failure record within the state dir.
	failureSuffix = "-failure.json"

	// sentinelKey is used when a payload carries no conversation id.
	sentinelKey = "session"
)

// cursorPayload is the subset of a Cursor hook's stdin payload cq reads.
//
// NOTE: field names match Cursor's wire format (snake_case); do not rename them
// to a Go convention — they are the external contract.
type cursorPayload struct {
	// ConversationID is Cursor's stable conversation identifier, used to key state.
	ConversationID string `json:"conversation_id"`

	// ToolName is the name of the tool the event concerns.
	ToolName string `json:"tool_name"`

	// ToolInput is the tool's raw input arguments.
	ToolInput map[string]any `json:"tool_input"`

	// ErrorMessage is the failure text on a post-tool-use-failure event.
	ErrorMessage string `json:"error_message"`

	// IsInterrupt reports whether the failure was a user interrupt rather than a real error.
	IsInterrupt bool `json:"is_interrupt"`
}

// failureRecord is cq's own state persisted between the post-tool-use-failure
// and stop events.
//
// NOTE: distinct from cursorPayload, which is Cursor's inbound wire schema; this
// record is ours, so it is not host-named.
type failureRecord struct {
	// ToolName is the tool that failed.
	ToolName string `json:"tool_name"`

	// Input is the formatted, length-bounded tool input.
	Input string `json:"input"`

	// Error is the truncated failure message.
	Error string `json:"error"`
}

// runCursor handles one Cursor lifecycle event.
//
// NOTE: the per-event helpers below are unprefixed because Cursor is the only
// host today.
// When a second host handler joins this package, give the host-specific helpers
// a host prefix or move each host into its own subpackage.
func runCursor(inv Invocation, in io.Reader, out io.Writer) error {
	if inv.Mode == ModePostToolUse {
		return nil
	}
	if err := os.MkdirAll(inv.StateDir, 0o700); err != nil {
		return fmt.Errorf("creating hook state directory: %w", err)
	}
	payload := readPayload(in)

	switch inv.Mode {
	case ModeSessionStart:
		return sweepState(inv.StateDir)
	case ModePostToolUseFailure:
		return recordFailure(inv.StateDir, payload)
	case ModeStop:
		return reportFailure(inv.StateDir, payload, out)
	default:
		return fmt.Errorf("unsupported cursor hook mode: %s", inv.Mode)
	}
}

// readPayload parses the event payload, degrading to an empty payload on empty
// or unparseable input so a hook never fails the agent over malformed stdin.
func readPayload(in io.Reader) cursorPayload {
	var p cursorPayload
	raw, err := io.ReadAll(io.LimitReader(in, maxPayloadBytes+1))
	if err != nil || len(raw) > maxPayloadBytes {
		return p
	}
	trimmed := bytes.TrimSpace(raw)
	if len(trimmed) == 0 {
		return p
	}
	// Fail open: unparseable stdin yields a zero payload rather than an error.
	_ = json.Unmarshal(trimmed, &p)
	return p
}

// recordFailure persists a failed tool call, skipping user interrupts.
func recordFailure(stateDir string, p cursorPayload) error {
	if p.IsInterrupt {
		return nil
	}
	if p.ToolName == "" && p.ErrorMessage == "" {
		return nil
	}
	path, err := statePath(stateDir, p)
	if err != nil {
		return err
	}
	data, err := json.Marshal(failureRecord{
		ToolName: p.ToolName,
		Input:    formatToolInput(p.ToolName, p.ToolInput),
		Error:    truncate(p.ErrorMessage, maxSnippetLength),
	})
	if err != nil {
		return fmt.Errorf("encoding hook failure record: %w", err)
	}
	if err := os.WriteFile(path, data, 0o600); err != nil {
		return fmt.Errorf("writing hook failure record: %w", err)
	}
	return nil
}

// reportFailure prints any recorded failure for the conversation, then clears it.
func reportFailure(stateDir string, p cursorPayload, out io.Writer) error {
	path, err := statePath(stateDir, p)
	if err != nil {
		return err
	}
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("reading hook failure record: %w", err)
	}
	var record failureRecord
	if err := json.Unmarshal(data, &record); err != nil {
		// A corrupt record is unrecoverable state cq wrote itself; discard it
		// rather than surface noise or fail the stop hook on every turn.
		return clearState(path)
	}
	_, _ = fmt.Fprintf(out, "cq: previous tool %s failed: %s\n  input: %s\n",
		record.ToolName, record.Error, record.Input)
	return clearState(path)
}

// clearState removes a consumed failure record, tolerating a concurrent delete.
func clearState(path string) error {
	if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("clearing hook failure record: %w", err)
	}
	return nil
}

// sweepState removes failure records older than the TTL.
func sweepState(stateDir string) error {
	entries, err := os.ReadDir(stateDir)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("reading hook state directory: %w", err)
	}
	cutoff := time.Now().Add(-stateTTL)
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), failureSuffix) {
			continue
		}
		info, err := entry.Info()
		if err != nil {
			continue
		}
		if info.ModTime().Before(cutoff) {
			// Best-effort cleanup: a record that resists removal is swept next time.
			_ = os.Remove(filepath.Join(stateDir, entry.Name()))
		}
	}
	return nil
}

// statePath returns the failure-record path for a conversation, guarding the
// untrusted conversation id against directory traversal.
func statePath(stateDir string, p cursorPayload) (string, error) {
	name := stateKey(p.ConversationID) + failureSuffix
	joined := filepath.Join(stateDir, name)
	if filepath.Dir(joined) != filepath.Clean(stateDir) {
		return "", fmt.Errorf("hook state path escapes the state directory")
	}
	return joined, nil
}

// stateKey reduces an untrusted conversation id to a filesystem-safe token,
// falling back to a sentinel when nothing usable remains.
func stateKey(id string) string {
	var b strings.Builder
	for _, r := range id {
		switch {
		case r >= 'a' && r <= 'z', r >= 'A' && r <= 'Z', r >= '0' && r <= '9', r == '-', r == '_':
			b.WriteRune(r)
		default:
			b.WriteRune('_')
		}
	}
	token := strings.Trim(b.String(), "_")
	if token == "" {
		return sentinelKey
	}
	return token
}

// formatToolInput renders a one-line, length-bounded summary of a tool call.
//
// NOTE: the tool-name set is best-effort; unrecognized tools fall through to a
// generic rendering, so an unknown or renamed Cursor tool degrades gracefully.
func formatToolInput(toolName string, input map[string]any) string {
	switch toolName {
	case "Shell", "Bash":
		return truncate(stringField(input, "command"), maxSnippetLength)
	case "Edit":
		return truncate(stringField(input, "file_path"), maxSnippetLength)
	case "Write":
		path := stringField(input, "path")
		if path == "" {
			path = stringField(input, "file_path")
		}
		return truncate(path+": "+stringField(input, "content"), maxSnippetLength)
	case "Read":
		return truncate(stringField(input, "file_path"), maxSnippetLength)
	default:
		return truncate(fmt.Sprintf("%s(%v)", toolName, input), maxSnippetLength)
	}
}

// stringField returns m[key] when it is a string, else the empty string.
func stringField(m map[string]any, key string) string {
	if v, ok := m[key].(string); ok {
		return v
	}
	return ""
}

// truncate shortens s to limit runes, appending an ellipsis when it was cut.
func truncate(s string, limit int) string {
	runes := []rune(s)
	if len(runes) <= limit {
		return s
	}
	return string(runes[:limit]) + "…"
}
