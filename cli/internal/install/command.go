package install

import "strings"

// transformCommand converts a Claude Code command file to OpenCode format by
// stripping the `name:` frontmatter line and inserting `agent: build`.
//
// Returns the source unchanged when YAML frontmatter is absent or unclosed.
func transformCommand(source string) string {
	lines := strings.SplitAfter(source, "\n")
	if len(lines) == 0 || strings.TrimRight(lines[0], "\r\n") != "---" {
		return source
	}

	out := []string{lines[0]}
	inFrontmatter := true
	closed := false
	for _, line := range lines[1:] {
		if inFrontmatter && strings.TrimRight(line, "\r\n") == "---" {
			out = append(out, "agent: build\n", line)
			inFrontmatter = false
			closed = true
			continue
		}
		if inFrontmatter && strings.HasPrefix(line, "name:") {
			continue
		}
		out = append(out, line)
	}

	if !closed {
		return source
	}
	return strings.Join(out, "")
}
