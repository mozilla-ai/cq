"""Canonical cq agent prompts.

Each prompt is synced into this package via ``make sync-prompts`` so SDK
consumers can surface the same text that the Claude Code and OpenCode slash
commands use.
"""

from importlib.resources import files


def reflect() -> str:
    """Return the /cq:reflect slash-command prompt.

    Returns:
        The Markdown body of the /cq:reflect slash command, synced from
        ``plugins/cq/commands/reflect.md`` via ``make sync-prompts``.
    """
    return files("cq.prompts").joinpath("reflect.md").read_text()


def skill() -> str:
    """Return the full cq agent skill prompt.

    Returns:
        The Markdown body of the cq agent skill, synced from
        ``plugins/cq/skills/cq/SKILL.md`` via ``make sync-prompts``.
    """
    return files("cq.prompts").joinpath("SKILL.md").read_text()
