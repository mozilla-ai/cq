"""Tests for write_if_missing / remove_owned_file primitives."""

from __future__ import annotations

import hashlib
from pathlib import Path

from cq_install.common import remove_owned_file, write_if_missing
from cq_install.context import Action

CONTENT = "rule body\n"
CONTENT_HASH = hashlib.sha256(CONTENT.encode()).hexdigest()


def test_write_if_missing_creates_file(tmp_path: Path):
    target = tmp_path / "rules" / "cq.mdc"
    result = write_if_missing(target, CONTENT, dry_run=False)
    assert result.action == Action.CREATED
    assert target.read_text() == CONTENT


def test_write_if_missing_unchanged_when_file_exists(tmp_path: Path):
    target = tmp_path / "rules" / "cq.mdc"
    target.parent.mkdir(parents=True)
    target.write_text("user edited\n")
    result = write_if_missing(target, CONTENT, dry_run=False)
    assert result.action == Action.UNCHANGED
    assert target.read_text() == "user edited\n"


def test_write_if_missing_dry_run_does_not_write(tmp_path: Path):
    target = tmp_path / "rules" / "cq.mdc"
    result = write_if_missing(target, CONTENT, dry_run=True)
    assert result.action == Action.CREATED
    assert not target.exists()


def test_remove_owned_file_removes_when_hash_matches(tmp_path: Path):
    target = tmp_path / "rules" / "cq.mdc"
    target.parent.mkdir(parents=True)
    target.write_text(CONTENT)
    result = remove_owned_file(target, expected_content_hash=CONTENT_HASH, dry_run=False)
    assert result.action == Action.REMOVED
    assert not target.exists()


def test_remove_owned_file_skips_when_user_edited(tmp_path: Path):
    target = tmp_path / "rules" / "cq.mdc"
    target.parent.mkdir(parents=True)
    target.write_text("user-edited\n")
    result = remove_owned_file(target, expected_content_hash=CONTENT_HASH, dry_run=False)
    assert result.action == Action.SKIPPED
    assert target.exists()


def test_remove_owned_file_no_op_when_missing(tmp_path: Path):
    target = tmp_path / "rules" / "cq.mdc"
    result = remove_owned_file(target, expected_content_hash=CONTENT_HASH, dry_run=False)
    assert result.action == Action.UNCHANGED


def test_remove_owned_file_removes_when_no_hash_provided(tmp_path: Path):
    target = tmp_path / "rules" / "cq.mdc"
    target.parent.mkdir(parents=True)
    target.write_text("anything\n")
    result = remove_owned_file(target, expected_content_hash=None, dry_run=False)
    assert result.action == Action.REMOVED
