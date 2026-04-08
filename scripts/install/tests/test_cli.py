"""Tests for the cq_install CLI dispatcher."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cq_install.cli import main


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a fake plugins/cq tree and point the CLI at it via env var."""
    plugin_root = tmp_path / "plugins" / "cq"
    (plugin_root / "scripts").mkdir(parents=True)
    (plugin_root / "scripts" / "bootstrap.py").write_text("# fake\n")
    (plugin_root / "skills" / "cq").mkdir(parents=True)
    (plugin_root / "skills" / "cq" / "SKILL.md").write_text("# cq\n")
    (plugin_root / "commands").mkdir()
    (plugin_root / "commands" / "cq-status.md").write_text("---\nname: cq-status\n---\nbody\n")
    monkeypatch.setenv("CQ_INSTALL_PLUGIN_ROOT", str(plugin_root))
    return plugin_root


def test_install_requires_at_least_one_target(fake_repo, capsys):
    with pytest.raises(SystemExit):
        main(["install", "--global"])
    captured = capsys.readouterr()
    assert "--target" in captured.err


def test_install_unknown_target_lists_valid_set(fake_repo, capsys):
    with pytest.raises(SystemExit):
        main(["install", "--target", "vscode", "--global"])
    captured = capsys.readouterr()
    assert "vscode" in captured.err
    assert "opencode" in captured.err


def test_install_global_and_project_are_mutually_exclusive(fake_repo, capsys, tmp_path):
    with pytest.raises(SystemExit):
        main(["install", "--target", "opencode", "--global", "--project", str(tmp_path / "p")])
    captured = capsys.readouterr()
    assert "--global" in captured.err or "mutually exclusive" in captured.err


def test_install_opencode_project(fake_repo, tmp_path):
    project = tmp_path / "myapp"
    project.mkdir()
    rc = main(["install", "--target", "opencode", "--project", str(project)])
    assert rc == 0
    config = json.loads((project / ".opencode" / "opencode.json").read_text())
    assert config["mcp"]["cq"]["type"] == "local"


def test_install_dry_run_does_not_write(fake_repo, tmp_path):
    project = tmp_path / "myapp"
    project.mkdir()
    rc = main(["install", "--target", "opencode", "--project", str(project), "--dry-run"])
    assert rc == 0
    assert not (project / ".opencode" / "opencode.json").exists()


def test_install_multi_target_dedups_shared_skills(fake_repo, tmp_path):
    project = tmp_path / "myapp"
    project.mkdir()
    # Cursor host reads cq_cursor_hook.py from the plugin tree; seed a fake.
    (fake_repo / "hooks" / "cursor").mkdir(parents=True, exist_ok=True)
    (fake_repo / "hooks" / "cursor" / "cq_cursor_hook.py").write_text("# fake\n")
    rc = main(
        [
            "install",
            "--target",
            "opencode",
            "--target",
            "cursor",
            "--project",
            str(project),
        ]
    )
    assert rc == 0
    assert (project / ".opencode" / "opencode.json").exists()
    assert (project / ".cursor" / "mcp.json").exists()
    # Shared skill commons installed exactly once even though both hosts asked.
    assert (project / ".agents" / "skills" / "cq" / "SKILL.md").exists()


def test_install_windsurf_project_is_invalid(fake_repo, tmp_path, capsys):
    project = tmp_path / "myapp"
    project.mkdir()
    rc = main(["install", "--target", "windsurf", "--project", str(project)])
    captured = capsys.readouterr()
    assert rc != 0
    assert "windsurf" in captured.err.lower()


def test_uninstall_opencode_project(fake_repo, tmp_path):
    project = tmp_path / "myapp"
    project.mkdir()
    main(["install", "--target", "opencode", "--project", str(project)])
    rc = main(["uninstall", "--target", "opencode", "--project", str(project)])
    assert rc == 0
    if (project / ".opencode" / "opencode.json").exists():
        config = json.loads((project / ".opencode" / "opencode.json").read_text())
        assert "mcp" not in config or "cq" not in config.get("mcp", {})
