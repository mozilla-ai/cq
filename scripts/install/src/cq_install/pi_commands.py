"""Pi command-file transform: strip `name:` frontmatter for Pi prompt files.

Pi derives a prompt's command name from its filename, not from a `name:`
frontmatter field, so the field is dropped. `description` is retained
(Pi shows it in autocomplete). The body is left intact; the cq block in
Pi's AGENTS.md redirects the body's MCP-tool wording to the cq CLI.
"""

from __future__ import annotations


def transform_command(source: str) -> str:
    """Return the Pi-flavored version of a Claude Code command file.

    Drops the `name:` line from the YAML frontmatter and rewrites `/cq:`
    slash-command references to `/cq-` so the body matches Pi's
    filename-derived command names (e.g. `/cq-status`). Returns the source
    unchanged when there is no frontmatter or the frontmatter is unclosed.
    """
    lines = source.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\n") != "---":
        return source

    out: list[str] = [lines[0]]
    in_frontmatter = True
    closed = False
    for line in lines[1:]:
        if in_frontmatter and line.rstrip("\n") == "---":
            out.append(line)
            in_frontmatter = False
            closed = True
            continue
        if in_frontmatter and line.startswith("name:"):
            continue
        out.append(line)

    if not closed:
        return source
    return "".join(out).replace("/cq:", "/cq-")
