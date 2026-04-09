"""Shared pytest fixtures for cq_install tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from cq_install.context import Action, ChangeResult


@pytest.fixture(autouse=True)
def _isolate_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate XDG_DATA_HOME to tmp_path for test isolation."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


@pytest.fixture(autouse=True)
def _stub_cq_binary_fetch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Stub the binary fetch so host install tests never hit the network.

    Host tests that want to assert the fetch happened can monkey-patch
    ``cq_install.binary.ensure_cq_binary`` with a different stub inside
    the test body. The default keeps the suite hermetic.
    """

    def _noop(plugin_root: Path, *, dry_run: bool = False) -> list[ChangeResult]:
        del plugin_root, dry_run
        return [
            ChangeResult(
                action=Action.UNCHANGED,
                path=tmp_path / "data" / "cq" / "runtime" / "bin" / "cq",
                detail="cq v0.2.0 (stubbed)",
            )
        ]

    monkeypatch.setattr("cq_install.binary.ensure_cq_binary", _noop)


@pytest.fixture
def plugin_root(tmp_path: Path) -> Path:
    """Build a fake `plugins/cq` tree under tmp_path that mirrors the real layout."""
    root = tmp_path / "plugins" / "cq"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text('{"name": "cq", "version": "0.6.0"}\n')
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "bootstrap.json").write_text('{"cli_version": "0.2.0"}\n')
    (root / "scripts" / "bootstrap.py").write_text("# fake bootstrap\n")
    (root / "scripts" / "cq_binary.py").write_text("# fake cq_binary\n")
    (root / "skills" / "cq").mkdir(parents=True)
    (root / "skills" / "cq" / "SKILL.md").write_text("# cq skill\n")
    (root / "commands").mkdir()
    (root / "commands" / "cq-status.md").write_text("---\nname: cq-status\n---\nbody\n")
    (root / "commands" / "cq-reflect.md").write_text("---\nname: cq-reflect\n---\nbody\n")
    return root
