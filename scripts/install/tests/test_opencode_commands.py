"""Tests for the OpenCode command frontmatter transform."""

from __future__ import annotations

from cq_install.opencode_commands import transform_command


def test_transform_strips_name_and_adds_agent():
    src = "---\nname: cq-status\ndescription: show status\n---\nbody\n"
    result = transform_command(src)
    assert "name: cq-status" not in result
    assert "agent: build" in result
    assert "description: show status" in result
    assert result.endswith("body\n")


def test_transform_preserves_body_with_dashes():
    src = "---\nname: cq-status\n---\n## Heading\n\n- bullet\n---\ntrailing\n"
    result = transform_command(src)
    assert "## Heading" in result
    assert "- bullet" in result
    assert "trailing" in result


def test_transform_no_frontmatter_passthrough():
    src = "no frontmatter here\n"
    result = transform_command(src)
    assert result == src
