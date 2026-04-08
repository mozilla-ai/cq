"""Tests for the OpenCode host install/uninstall flow."""

from __future__ import annotations

import json
from pathlib import Path

from cq_install.content import PYTHON_COMMAND
from cq_install.context import Action, InstallContext, RunState
from cq_install.hosts.opencode import (
    OPENCODE_CONFIG_DIR_ENV,
    OPENCODE_SCHEMA_URL,
    OpenCodeHost,
)


def test_opencode_global_target_default(monkeypatch):
    """Without OPENCODE_CONFIG_DIR the default is ~/.config/opencode."""
    monkeypatch.delenv(OPENCODE_CONFIG_DIR_ENV, raising=False)
    target = OpenCodeHost().global_target()
    assert target == Path.home() / ".config" / "opencode"


def test_opencode_global_target_honors_env_override(tmp_path, monkeypatch):
    """OPENCODE_CONFIG_DIR overrides the default, matching OpenCode's own resolution."""
    override = tmp_path / "custom-opencode"
    monkeypatch.setenv(OPENCODE_CONFIG_DIR_ENV, str(override))
    target = OpenCodeHost().global_target()
    assert target == override.resolve()


def _ctx(tmp_path: Path, plugin_root: Path, *, host_isolated: bool = False) -> InstallContext:
    target = tmp_path / "target"
    target.mkdir(exist_ok=True)
    return InstallContext(
        target=target,
        plugin_root=plugin_root,
        bootstrap_path=plugin_root / "scripts" / "bootstrap.py",
        shared_skills_path=tmp_path / "shared",
        host_isolated_skills=host_isolated,
        dry_run=False,
        run_state=RunState(),
    )


def test_opencode_install_writes_mcp_config(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    OpenCodeHost().install(ctx)

    config = json.loads((ctx.target / "opencode.json").read_text())
    assert config["mcp"]["cq"]["type"] == "local"
    # Literal python command name resolved by PATH at OpenCode's invocation time.
    assert config["mcp"]["cq"]["command"][0] == PYTHON_COMMAND
    assert config["mcp"]["cq"]["command"][1].endswith("bootstrap.py")


def test_opencode_install_seeds_schema_on_fresh_create(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    OpenCodeHost().install(ctx)

    config = json.loads((ctx.target / "opencode.json").read_text())
    assert config["$schema"] == OPENCODE_SCHEMA_URL


def test_opencode_install_does_not_touch_schema_on_existing_file(tmp_path, plugin_root):
    config_file = tmp_path / "target" / "opencode.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(json.dumps({"$schema": "https://example.com/custom.json"}))
    ctx = _ctx(tmp_path, plugin_root)
    OpenCodeHost().install(ctx)
    config = json.loads(config_file.read_text())
    assert config["$schema"] == "https://example.com/custom.json"


def test_opencode_install_generates_command_files(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    OpenCodeHost().install(ctx)

    cmd = (ctx.target / "commands" / "cq-status.md").read_text()
    assert "agent: build" in cmd
    assert "name: cq-status" not in cmd


def test_opencode_install_appends_agents_md_block(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    OpenCodeHost().install(ctx)

    text = (ctx.target / "AGENTS.md").read_text()
    assert "<!-- cq:start -->" in text
    assert "<!-- cq:end -->" in text


def test_opencode_install_shared_skills_default(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root, host_isolated=False)
    OpenCodeHost().install(ctx)
    assert (ctx.shared_skills_path / "cq" / "SKILL.md").exists()
    assert not (ctx.target / "skills").exists()


def test_opencode_install_host_isolated_copies_skills_into_target(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root, host_isolated=True)
    OpenCodeHost().install(ctx)
    assert (ctx.target / "skills" / "cq" / "SKILL.md").exists()


def test_opencode_install_idempotent(tmp_path, plugin_root):
    OpenCodeHost().install(_ctx(tmp_path, plugin_root))
    second = OpenCodeHost().install(_ctx(tmp_path, plugin_root))
    actions = [r.action for r in second]
    assert all(a in (Action.UNCHANGED, Action.CREATED) for a in actions)
    assert any(a == Action.UNCHANGED for a in actions)


def test_opencode_install_replaces_stale_mcp_command(tmp_path, plugin_root):
    config_file = tmp_path / "target" / "opencode.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(
        json.dumps(
            {
                "mcp": {
                    "cq": {
                        "type": "local",
                        "command": ["uv", "run", "cq-mcp-server"],
                    }
                }
            }
        )
    )
    ctx = _ctx(tmp_path, plugin_root)
    OpenCodeHost().install(ctx)
    config = json.loads(config_file.read_text())
    assert config["mcp"]["cq"]["command"][0] == PYTHON_COMMAND


def test_opencode_install_preserves_user_added_mcp_field(tmp_path, plugin_root):
    config_file = tmp_path / "target" / "opencode.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(
        json.dumps(
            {
                "mcp": {
                    "cq": {
                        "type": "local",
                        "command": ["old"],
                        "env": {"CQ_API_KEY": "secret"},  # pragma: allowlist secret
                    }
                }
            }
        )
    )
    ctx = _ctx(tmp_path, plugin_root)
    OpenCodeHost().install(ctx)
    config = json.loads(config_file.read_text())
    assert config["mcp"]["cq"]["env"] == {"CQ_API_KEY": "secret"}  # pragma: allowlist secret


def test_opencode_uninstall_removes_assets(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    OpenCodeHost().install(ctx)
    OpenCodeHost().uninstall(ctx)
    assert not (ctx.target / "commands" / "cq-status.md").exists()
    config = json.loads((ctx.target / "opencode.json").read_text())
    assert "mcp" not in config or "cq" not in config.get("mcp", {})
    text = (ctx.target / "AGENTS.md").read_text() if (ctx.target / "AGENTS.md").exists() else ""
    assert "<!-- cq:start -->" not in text
