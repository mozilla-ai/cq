package hook

import (
	"bytes"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

// invoke runs one Cursor lifecycle event through Run.
func invoke(mode Mode, stateDir string, in io.Reader, out io.Writer) error {
	return Run(Invocation{Host: HostCursor, Mode: mode, StateDir: stateDir}, in, out)
}

func TestAllowedHostsListsRegistered(t *testing.T) {
	require.Equal(t, Hosts{HostCursor}, AllowedHosts())
}

func TestHostSetValidatesAndNormalizes(t *testing.T) {
	var h Host
	require.NoError(t, h.Set("CURSOR"))
	require.Equal(t, HostCursor, h)

	err := (&h).Set("emacs")
	require.Error(t, err)
	require.Contains(t, err.Error(), "unsupported hook host emacs")
	require.Contains(t, err.Error(), "cursor")
}

func TestModeSetValidates(t *testing.T) {
	var m Mode
	require.NoError(t, m.Set("stop"))
	require.Equal(t, ModeStop, m)

	err := (&m).Set("no-such-mode")
	require.Error(t, err)
	require.Contains(t, err.Error(), "unsupported hook mode no-such-mode")
	require.Contains(t, err.Error(), "session-start")
}

func TestRunRejectsUnknownHostAndMode(t *testing.T) {
	dir := t.TempDir()
	require.Error(
		t,
		Run(Invocation{Host: "nope", Mode: ModeStop, StateDir: dir}, strings.NewReader("{}"), &bytes.Buffer{}),
	)
	require.Error(t, invoke("no-such-mode", dir, strings.NewReader("{}"), &bytes.Buffer{}))
}

func TestCursorCaptureThenSurfaceAtStop(t *testing.T) {
	dir := t.TempDir()
	payload := `{"conversation_id":"abc","tool_name":"Bash","tool_input":{"command":"make test"},"error_message":"exit 1","is_interrupt":false}`

	require.NoError(t, invoke(ModePostToolUseFailure, dir, strings.NewReader(payload), &bytes.Buffer{}))
	require.FileExists(t, filepath.Join(dir, "abc-failure.json"))

	var out bytes.Buffer
	require.NoError(t, invoke(ModeStop, dir, strings.NewReader(`{"conversation_id":"abc","status":"completed"}`), &out))
	require.Contains(t, out.String(), "previous tool Bash failed: exit 1")
	require.Contains(t, out.String(), "make test")
	require.NoFileExists(t, filepath.Join(dir, "abc-failure.json"))
}

func TestCursorInterruptIsNotCaptured(t *testing.T) {
	dir := t.TempDir()
	payload := `{"conversation_id":"abc","tool_name":"Bash","is_interrupt":true}`
	require.NoError(t, invoke(ModePostToolUseFailure, dir, strings.NewReader(payload), &bytes.Buffer{}))
	require.NoFileExists(t, filepath.Join(dir, "abc-failure.json"))
}

func TestCursorStopWithoutFailureIsSilent(t *testing.T) {
	dir := t.TempDir()
	var out bytes.Buffer
	require.NoError(t, invoke(ModeStop, dir, strings.NewReader(`{"conversation_id":"abc"}`), &out))
	require.Empty(t, out.String())
}

func TestCursorMissingConversationIDUsesSentinel(t *testing.T) {
	dir := t.TempDir()
	payload := `{"tool_name":"Read","tool_input":{"file_path":"a.go"},"error_message":"boom"}`
	require.NoError(t, invoke(ModePostToolUseFailure, dir, strings.NewReader(payload), &bytes.Buffer{}))
	require.FileExists(t, filepath.Join(dir, "session-failure.json"))
}

func TestCursorConversationIDCannotEscapeStateDir(t *testing.T) {
	dir := t.TempDir()
	payload := `{"conversation_id":"../../etc/evil","tool_name":"X","error_message":"e"}`
	require.NoError(t, invoke(ModePostToolUseFailure, dir, strings.NewReader(payload), &bytes.Buffer{}))
	// No file is written outside the state dir.
	entries, err := os.ReadDir(dir)
	require.NoError(t, err)
	for _, e := range entries {
		require.True(t, strings.HasSuffix(e.Name(), "-failure.json"))
	}
	parent := filepath.Dir(dir)
	_, statErr := os.Stat(filepath.Join(parent, "etc", "evil-failure.json"))
	require.True(t, os.IsNotExist(statErr))
}

func TestCursorStopDiscardsCorruptRecord(t *testing.T) {
	dir := t.TempDir()
	require.NoError(t, os.WriteFile(filepath.Join(dir, "abc-failure.json"), []byte("{not json"), 0o644))
	var out bytes.Buffer
	require.NoError(t, invoke(ModeStop, dir, strings.NewReader(`{"conversation_id":"abc"}`), &out))
	require.Empty(t, out.String())
	require.NoFileExists(t, filepath.Join(dir, "abc-failure.json"))
}

func TestCursorEmptyStdinDoesNotPanic(t *testing.T) {
	dir := t.TempDir()
	require.NoError(t, invoke(ModePostToolUseFailure, dir, strings.NewReader(""), &bytes.Buffer{}))
	require.NoError(t, invoke(ModeStop, dir, strings.NewReader("   "), &bytes.Buffer{}))
}

func TestCursorSessionStartSweepsStaleState(t *testing.T) {
	dir := t.TempDir()
	stale := filepath.Join(dir, "old-failure.json")
	require.NoError(t, os.WriteFile(stale, []byte("{}"), 0o644))
	old := time.Now().Add(-48 * time.Hour)
	require.NoError(t, os.Chtimes(stale, old, old))

	fresh := filepath.Join(dir, "new-failure.json")
	require.NoError(t, os.WriteFile(fresh, []byte("{}"), 0o644))

	require.NoError(t, invoke(ModeSessionStart, dir, strings.NewReader(`{"conversation_id":"x"}`), &bytes.Buffer{}))
	require.NoFileExists(t, stale)
	require.FileExists(t, fresh)
}

func TestFormatToolInputShapes(t *testing.T) {
	require.Equal(t, "make test", formatToolInput("Bash", map[string]any{"command": "make test"}))
	require.Equal(t, "a.go", formatToolInput("Edit", map[string]any{"file_path": "a.go"}))
	require.Equal(t, "a.go: hi", formatToolInput("Write", map[string]any{"path": "a.go", "content": "hi"}))
	require.Equal(t, "x.go", formatToolInput("Read", map[string]any{"file_path": "x.go"}))
	require.Contains(t, formatToolInput("Other", map[string]any{"k": "v"}), "Other(")
}

func TestTruncateIsRuneSafe(t *testing.T) {
	require.Equal(t, "ab", truncate("ab", 5))
	require.Equal(t, "ab…", truncate("abcde", 2))
	// Marshalable check: the record round-trips through JSON.
	rec := failureRecord{ToolName: "Bash", Input: "x", Error: "y"}
	data, err := json.Marshal(rec)
	require.NoError(t, err)
	require.Contains(t, string(data), `"tool_name":"Bash"`)
}
