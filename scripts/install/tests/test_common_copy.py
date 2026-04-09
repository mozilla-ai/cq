"""Tests for copy_tree / remove_copied_tree primitives in common.py."""

from __future__ import annotations

import json
from pathlib import Path

from cq_install.common import copy_tree, remove_copied_tree
from cq_install.context import Action

MANIFEST_NAME = ".cq-install-manifest.json"


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def test_copy_tree_creates_files_and_manifest(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    _write(src / "cq" / "SKILL.md", "# cq\n")
    _write(src / "cq" / "references" / "foo.md", "foo\n")

    result = copy_tree(src, dst, manifest_name=MANIFEST_NAME, dry_run=False)
    assert result.action == Action.CREATED
    assert (dst / "cq" / "SKILL.md").read_text() == "# cq\n"
    assert (dst / "cq" / "references" / "foo.md").read_text() == "foo\n"

    manifest = json.loads((dst / MANIFEST_NAME).read_text())
    paths = {entry["path"] for entry in manifest["files"]}
    assert paths == {"cq/SKILL.md", "cq/references/foo.md"}


def test_copy_tree_unchanged_on_repeat(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    _write(src / "cq" / "SKILL.md", "# cq\n")

    copy_tree(src, dst, manifest_name=MANIFEST_NAME, dry_run=False)
    result = copy_tree(src, dst, manifest_name=MANIFEST_NAME, dry_run=False)
    assert result.action == Action.UNCHANGED


def test_copy_tree_updates_when_source_changes(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    _write(src / "cq" / "SKILL.md", "# v1\n")
    copy_tree(src, dst, manifest_name=MANIFEST_NAME, dry_run=False)

    _write(src / "cq" / "SKILL.md", "# v2\n")
    result = copy_tree(src, dst, manifest_name=MANIFEST_NAME, dry_run=False)
    assert result.action == Action.UPDATED
    assert (dst / "cq" / "SKILL.md").read_text() == "# v2\n"


def test_copy_tree_removes_files_no_longer_in_source(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    _write(src / "cq" / "SKILL.md", "# cq\n")
    _write(src / "cq" / "extra.md", "extra\n")
    copy_tree(src, dst, manifest_name=MANIFEST_NAME, dry_run=False)

    (src / "cq" / "extra.md").unlink()
    result = copy_tree(src, dst, manifest_name=MANIFEST_NAME, dry_run=False)
    assert result.action == Action.UPDATED
    assert not (dst / "cq" / "extra.md").exists()


def test_copy_tree_dry_run_does_not_write(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    _write(src / "cq" / "SKILL.md", "# cq\n")
    result = copy_tree(src, dst, manifest_name=MANIFEST_NAME, dry_run=True)
    assert result.action == Action.CREATED
    assert not dst.exists()


def test_remove_copied_tree_deletes_manifest_files(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    _write(src / "cq" / "SKILL.md", "# cq\n")
    _write(src / "cq" / "references" / "foo.md", "foo\n")
    copy_tree(src, dst, manifest_name=MANIFEST_NAME, dry_run=False)

    result = remove_copied_tree(dst, manifest_name=MANIFEST_NAME, dry_run=False)
    assert result.action == Action.REMOVED
    assert not (dst / "cq" / "SKILL.md").exists()
    assert not (dst / MANIFEST_NAME).exists()


def test_remove_copied_tree_skips_user_modified_files(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    _write(src / "cq" / "SKILL.md", "# cq\n")
    copy_tree(src, dst, manifest_name=MANIFEST_NAME, dry_run=False)

    (dst / "cq" / "SKILL.md").write_text("# user-edited\n")
    result = remove_copied_tree(dst, manifest_name=MANIFEST_NAME, dry_run=False)
    assert result.action == Action.SKIPPED
    assert (dst / "cq" / "SKILL.md").read_text() == "# user-edited\n"


def test_remove_copied_tree_no_op_without_manifest(tmp_path: Path):
    dst = tmp_path / "dst"
    dst.mkdir()
    result = remove_copied_tree(dst, manifest_name=MANIFEST_NAME, dry_run=False)
    assert result.action == Action.UNCHANGED
