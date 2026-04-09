"""Tests for Markdown block primitives in common.py."""

from __future__ import annotations

from pathlib import Path

from cq_install.common import remove_markdown_block, upsert_markdown_block
from cq_install.context import Action

START = "<!-- cq:start -->"
END = "<!-- cq:end -->"
BLOCK = f"{START}\n## CQ\n\nUse the cq skill.\n{END}"


def test_upsert_creates_file_with_block(tmp_path: Path):
    target = tmp_path / "AGENTS.md"
    result = upsert_markdown_block(target, START, END, BLOCK, dry_run=False)
    assert result.action == Action.CREATED
    assert START in target.read_text()
    assert END in target.read_text()


def test_upsert_appends_to_existing_file_and_returns_updated(tmp_path: Path):
    target = tmp_path / "AGENTS.md"
    target.write_text("# Existing\n\nUser content.\n")
    result = upsert_markdown_block(target, START, END, BLOCK, dry_run=False)
    text = target.read_text()
    assert "User content." in text
    assert START in text
    assert result.action == Action.UPDATED


def test_upsert_unchanged_when_block_present_and_identical(tmp_path: Path):
    target = tmp_path / "AGENTS.md"
    upsert_markdown_block(target, START, END, BLOCK, dry_run=False)
    result = upsert_markdown_block(target, START, END, BLOCK, dry_run=False)
    assert result.action == Action.UNCHANGED


def test_upsert_replaces_block_when_content_changes(tmp_path: Path):
    target = tmp_path / "AGENTS.md"
    upsert_markdown_block(target, START, END, BLOCK, dry_run=False)
    new_block = f"{START}\n## CQ v2\n{END}"
    result = upsert_markdown_block(target, START, END, new_block, dry_run=False)
    assert result.action == Action.UPDATED
    text = target.read_text()
    assert "## CQ v2" in text
    assert "Use the cq skill." not in text


def test_upsert_dry_run_does_not_write(tmp_path: Path):
    target = tmp_path / "AGENTS.md"
    result = upsert_markdown_block(target, START, END, BLOCK, dry_run=True)
    assert result.action == Action.CREATED
    assert not target.exists()


def test_remove_block_strips_section(tmp_path: Path):
    target = tmp_path / "AGENTS.md"
    target.write_text(f"# Existing\n\nUser content.\n\n{BLOCK}\n")
    result = remove_markdown_block(target, START, END, dry_run=False)
    assert result.action == Action.REMOVED
    text = target.read_text()
    assert "User content." in text
    assert START not in text
    assert END not in text


def test_remove_block_deletes_file_when_empty_after_strip(tmp_path: Path):
    target = tmp_path / "AGENTS.md"
    target.write_text(f"{BLOCK}\n")
    remove_markdown_block(target, START, END, dry_run=False)
    assert not target.exists()


def test_remove_block_no_op_when_marker_absent(tmp_path: Path):
    target = tmp_path / "AGENTS.md"
    target.write_text("# Existing\n")
    result = remove_markdown_block(target, START, END, dry_run=False)
    assert result.action == Action.UNCHANGED
