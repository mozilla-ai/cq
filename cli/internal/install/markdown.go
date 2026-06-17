package install

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// cqBlock is the marker pair used by all cq-managed blocks in instruction
// files (AGENTS.md).
var cqBlock = blockMarkers{
	start: "<!-- cq:start -->",
	end:   "<!-- cq:end -->",
}

// blockMarkers identifies the start and end delimiters of a managed block
// within a markdown file.
type blockMarkers struct {
	start string
	end   string
}

// upsertMarkdownBlock inserts or replaces a delimited block in a markdown file.
//
// content must include the start and end markers.
// When the file is absent, it is created with content as the body.
// When the file exists but contains no start marker, the block is appended
// with a blank-line separator.
// When the block is present but unchanged, UNCHANGED is returned.
// When the start marker is present without a matching end marker, the file
// is left untouched and SKIPPED is returned.
func upsertMarkdownBlock(file string, markers blockMarkers, content string, dryRun bool) (Change, error) {
	text, err := readFileOrEmpty(file)
	if err != nil {
		return Change{}, fmt.Errorf("reading instruction file: %w", err)
	}
	if text == "" {
		return writeNewFile(file, content+"\n", dryRun)
	}

	startIdx := strings.Index(text, markers.start)
	if startIdx == -1 {
		return writeFile(file, strings.TrimRight(text, "\r\n")+"\n\n"+content+"\n", ActionUpdated, dryRun)
	}

	endRel := strings.Index(text[startIdx+len(markers.start):], markers.end)
	if endRel == -1 {
		return Change{
			Action: ActionSkipped,
			Path:   file,
			Detail: "start marker present without matching end marker",
		}, nil
	}
	endIdx := startIdx + len(markers.start) + endRel

	blockEnd := endIdx + len(markers.end)
	if text[startIdx:blockEnd] == content {
		return Change{Action: ActionUnchanged, Path: file}, nil
	}
	return writeFile(file, text[:startIdx]+content+text[blockEnd:], ActionUpdated, dryRun)
}

// removeMarkdownBlock removes a delimited block from a markdown file.
//
// When the file becomes empty after removal, it is deleted.
// When the start marker is present without a matching end marker, the file
// is left untouched and SKIPPED is returned.
func removeMarkdownBlock(file string, markers blockMarkers, dryRun bool) (Change, error) {
	data, err := os.ReadFile(file)
	if os.IsNotExist(err) {
		return Change{Action: ActionUnchanged, Path: file}, nil
	}
	if err != nil {
		return Change{}, fmt.Errorf("reading instruction file: %w", err)
	}

	text := string(data)
	startIdx := strings.Index(text, markers.start)
	if startIdx == -1 {
		return Change{Action: ActionUnchanged, Path: file}, nil
	}

	endRel := strings.Index(text[startIdx+len(markers.start):], markers.end)
	if endRel == -1 {
		return Change{
			Action: ActionSkipped,
			Path:   file,
			Detail: "start marker present without matching end marker",
		}, nil
	}
	endIdx := startIdx + len(markers.start) + endRel

	newText := joinSurrounding(
		strings.TrimRight(text[:startIdx], "\r\n"),
		strings.TrimLeft(text[endIdx+len(markers.end):], "\r\n"),
	)

	newText = strings.TrimRight(newText, "\r\n")
	if newText == "" {
		return removeFile(file, dryRun)
	}
	return writeFile(file, newText+"\n", ActionRemoved, dryRun)
}

// joinSurrounding reassembles the text before and after a removed block,
// collapsing to a single blank-line separator when both are non-empty.
func joinSurrounding(before string, after string) string {
	switch {
	case before == "" && after == "":
		return ""
	case before == "":
		return after
	case after == "":
		return before
	default:
		return before + "\n\n" + after
	}
}

// readFileOrEmpty reads file and returns its content, or "" when absent.
func readFileOrEmpty(file string) (string, error) {
	data, err := os.ReadFile(file)
	if os.IsNotExist(err) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return string(data), nil
}

// removeFile deletes a file, reporting REMOVED.
func removeFile(file string, dryRun bool) (Change, error) {
	if dryRun {
		return Change{Action: ActionRemoved, Path: file}, nil
	}
	if err := os.Remove(file); err != nil {
		return Change{}, fmt.Errorf("removing empty instruction file: %w", err)
	}
	return Change{Action: ActionRemoved, Path: file}, nil
}

// writeFile overwrites an existing file with content, reporting the given action.
func writeFile(file string, content string, action Action, dryRun bool) (Change, error) {
	if dryRun {
		return Change{Action: action, Path: file}, nil
	}
	if err := os.WriteFile(file, []byte(content), 0o644); err != nil {
		return Change{}, fmt.Errorf("writing instruction file: %w", err)
	}
	return Change{Action: action, Path: file}, nil
}

// writeNewFile creates a new file with the given content, creating parent
// directories as needed.
func writeNewFile(file string, content string, dryRun bool) (Change, error) {
	if dryRun {
		return Change{Action: ActionCreated, Path: file}, nil
	}
	if err := os.MkdirAll(filepath.Dir(file), 0o755); err != nil {
		return Change{}, fmt.Errorf("creating directory for instruction file: %w", err)
	}
	if err := os.WriteFile(file, []byte(content), 0o644); err != nil {
		return Change{}, fmt.Errorf("writing instruction file: %w", err)
	}
	return Change{Action: ActionCreated, Path: file}, nil
}
