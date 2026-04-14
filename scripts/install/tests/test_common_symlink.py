"""Tests for symlink_tree primitive."""

from __future__ import annotations

from pathlib import Path

from cq_install.common import symlink_tree
from cq_install.context import Action


def test_symlink_tree_creates_link(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "x.md").write_text("x\n")
    dst = tmp_path / "dst"

    result = symlink_tree(src, dst, dry_run=False)
    assert result.action == Action.CREATED
    assert dst.is_symlink()
    assert dst.resolve() == src.resolve()


def test_symlink_tree_unchanged_when_already_pointing_at_src(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "dst"
    symlink_tree(src, dst, dry_run=False)
    result = symlink_tree(src, dst, dry_run=False)
    assert result.action == Action.UNCHANGED


def test_symlink_tree_updates_when_pointing_elsewhere(tmp_path: Path):
    real_src = tmp_path / "real"
    real_src.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    dst = tmp_path / "dst"
    dst.symlink_to(other)

    result = symlink_tree(real_src, dst, dry_run=False)
    assert result.action == Action.UPDATED
    assert dst.resolve() == real_src.resolve()


def test_symlink_tree_dry_run_does_not_write(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "dst"
    result = symlink_tree(src, dst, dry_run=True)
    assert result.action == Action.CREATED
    assert not dst.exists()
