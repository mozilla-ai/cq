"""Protocol module exposing the canonical cq agent skill prompt."""

from importlib.resources import files


def prompt() -> str:
    """Return the full cq agent protocol prompt."""
    return files("cq.protocol").joinpath("skill.md").read_text()
