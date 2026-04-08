"""Tests for the Windsurf host install/uninstall flow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cq_install.content import PYTHON_COMMAND
from cq_install.context import Action, InstallContext, RunState
from cq_install.hosts.windsurf import WindsurfHost


def _ctx(tmp_path: Path, plugin_root: Path) -> InstallContext:
    target = tmp_path / "target"
    target.mkdir(exist_ok=True)
    return InstallContext(
        target=target,
        plugin_root=plugin_root,
        bootstrap_path=plugin_root / "scripts" / "bootstrap.py",
        shared_skills_path=tmp_path / "shared",
        host_isolated_skills=False,
        dry_run=False,
        run_state=RunState(),
    )


def test_windsurf_does_not_support_project():
    assert WindsurfHost().supports_project is False
    with pytest.raises(NotImplementedError):
        WindsurfHost().project_target(Path("/tmp"))


def test_windsurf_install_writes_mcp_config(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    WindsurfHost().install(ctx)
    config = json.loads((ctx.target / "mcp_config.json").read_text())
    assert config["mcpServers"]["cq"]["command"] == PYTHON_COMMAND
    assert config["mcpServers"]["cq"]["args"][0].endswith("bootstrap.py")


def test_windsurf_install_creates_shared_skills(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    WindsurfHost().install(ctx)
    assert (ctx.shared_skills_path / "cq" / "SKILL.md").exists()


def test_windsurf_install_idempotent(tmp_path, plugin_root):
    WindsurfHost().install(_ctx(tmp_path, plugin_root))
    second = WindsurfHost().install(_ctx(tmp_path, plugin_root))
    assert any(r.action == Action.UNCHANGED for r in second)


def test_windsurf_uninstall_removes_mcp_entry(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    WindsurfHost().install(ctx)
    WindsurfHost().uninstall(ctx)
    config_path = ctx.target / "mcp_config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        assert "mcpServers" not in config or "cq" not in config.get("mcpServers", {})
