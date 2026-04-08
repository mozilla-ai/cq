"""OpenCode command file transform: strip `name:` frontmatter, add `agent: build`."""

from __future__ import annotations


def transform_command(source: str) -> str:
    """Return the OpenCode-flavored version of a Claude Code command file."""
    lines = source.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\n") != "---":
        return source

    out: list[str] = [lines[0]]
    in_frontmatter = True
    closed = False
    for line in lines[1:]:
        if in_frontmatter and line.rstrip("\n") == "---":
            out.append("agent: build\n")
            out.append(line)
            in_frontmatter = False
            closed = True
            continue
        if in_frontmatter and line.startswith("name:"):
            continue
        out.append(line)

    if not closed:
        return source
    return "".join(out)
