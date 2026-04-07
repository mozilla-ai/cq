"""Shared pytest fixtures for cq_install tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def plugin_root(tmp_path: Path) -> Path:
    """Build a fake `plugins/cq` tree under tmp_path that mirrors the real layout."""
    root = tmp_path / "plugins" / "cq"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "bootstrap.py").write_text("# fake bootstrap\n")
    (root / "skills" / "cq").mkdir(parents=True)
    (root / "skills" / "cq" / "SKILL.md").write_text("# cq skill\n")
    (root / "commands").mkdir()
    (root / "commands" / "cq-status.md").write_text("---\nname: cq-status\n---\nbody\n")
    (root / "commands" / "cq-reflect.md").write_text("---\nname: cq-reflect\n---\nbody\n")
    return root
