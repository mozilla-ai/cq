"""Tests for the Pi command-file transform."""

from __future__ import annotations

from cq_install.pi_commands import transform_command


def test_transform_drops_name_frontmatter_keeps_description():
    src = "---\nname: cq:status\ndescription: Show status.\n---\nbody line\n"
    out = transform_command(src)
    assert "name: cq:status" not in out
    assert "description: Show status." in out
    assert "body line" in out
    assert out.startswith("---\n")


def test_transform_rewrites_colon_command_refs_to_dash():
    src = "---\nname: cq:status\ndescription: x\n---\n# /cq:status\nsee the /cq:reflect command\n"
    out = transform_command(src)
    assert "/cq-status" in out
    assert "/cq-reflect" in out
    assert "/cq:status" not in out
    assert "/cq:reflect" not in out


def test_transform_returns_source_when_no_frontmatter():
    src = "no frontmatter here\n"
    assert transform_command(src) == src


def test_transform_returns_source_when_frontmatter_unclosed():
    src = "---\nname: cq:status\nbody without closing fence\n"
    assert transform_command(src) == src
