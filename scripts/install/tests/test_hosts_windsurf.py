"""Tests for the Windsurf host install/uninstall flow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cq_install.content import cq_binary_name
from cq_install.context import Action, InstallContext, RunState
from cq_install.hosts.windsurf import WindsurfHost
from cq_install.runtime import runtime_root

RUNTIME_BINARY = Path("bin") / cq_binary_name()


def _ctx(tmp_path: Path, plugin_root: Path) -> InstallContext:
    target = tmp_path / "target"
    target.mkdir(exist_ok=True)
    return InstallContext(
        target=target,
        plugin_root=plugin_root,
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
    shared_runtime = runtime_root()
    WindsurfHost().install(ctx)
    config = json.loads((ctx.target / "mcp_config.json").read_text())
    assert config["mcpServers"]["cq"]["command"] == str(shared_runtime / RUNTIME_BINARY)
    assert config["mcpServers"]["cq"]["args"] == ["mcp"]


def test_windsurf_install_does_not_copy_bootstrap_to_runtime(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    shared_runtime = runtime_root()
    WindsurfHost().install(ctx)
    assert not (shared_runtime / "scripts" / "bootstrap.py").exists()
    assert not (shared_runtime / "scripts" / "bootstrap.json").exists()


def test_windsurf_install_calls_ensure_cq_binary(tmp_path, plugin_root, monkeypatch):
    fetch_calls: list[Path] = []

    def _record(plugin_root_arg: Path, *, dry_run: bool = False):
        from cq_install.context import ChangeResult

        del dry_run
        fetch_calls.append(plugin_root_arg)
        return [
            ChangeResult(
                action=Action.CREATED,
                path=runtime_root() / "bin" / cq_binary_name(),
                detail="cq v0.2.0",
            )
        ]

    monkeypatch.setattr("cq_install.binary.ensure_cq_binary", _record)

    ctx = _ctx(tmp_path, plugin_root)
    results = WindsurfHost().install(ctx)

    assert fetch_calls == [plugin_root]
    assert any(r.detail == "cq v0.2.0" for r in results)


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
