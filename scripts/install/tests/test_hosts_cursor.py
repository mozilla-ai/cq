"""Tests for the Cursor host install/uninstall flow."""

from __future__ import annotations

import json
from pathlib import Path

from cq_install.content import PYTHON_COMMAND, cq_binary_name
from cq_install.context import Action, InstallContext, RunState
from cq_install.hosts.cursor import CursorHost
from cq_install.runtime import runtime_root

RUNTIME_BINARY = Path("bin") / cq_binary_name()
RUNTIME_HOOK = Path("hooks") / "cursor" / "cq_cursor_hook.py"


def _ctx(tmp_path: Path, plugin_root: Path) -> InstallContext:
    target = tmp_path / "target"
    target.mkdir(exist_ok=True)
    (plugin_root / "hooks" / "cursor").mkdir(parents=True, exist_ok=True)
    (plugin_root / "hooks" / "cursor" / "cq_cursor_hook.py").write_text("# fake\n")
    return InstallContext(
        target=target,
        plugin_root=plugin_root,
        shared_skills_path=tmp_path / "shared",
        host_isolated_skills=False,
        dry_run=False,
        run_state=RunState(),
    )


def test_cursor_install_writes_mcp_servers_entry(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    shared_runtime = runtime_root()
    CursorHost().install(ctx)

    config = json.loads((ctx.target / "mcp.json").read_text())
    assert config["mcpServers"]["cq"]["command"] == str(shared_runtime / RUNTIME_BINARY)
    assert config["mcpServers"]["cq"]["args"] == ["mcp"]
    assert (shared_runtime / RUNTIME_HOOK).exists()


def test_cursor_install_runtime_bundle_contains_only_hook_script(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    shared_runtime = runtime_root()
    CursorHost().install(ctx)

    assert (shared_runtime / RUNTIME_HOOK).exists()
    assert not (shared_runtime / "scripts" / "bootstrap.py").exists()
    assert not (shared_runtime / "scripts" / "bootstrap.json").exists()


def test_cursor_install_calls_ensure_cq_binary(tmp_path, plugin_root, monkeypatch):
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
    results = CursorHost().install(ctx)

    assert fetch_calls == [plugin_root]
    assert any(r.detail == "cq v0.2.0" for r in results)


def test_cursor_install_hook_command_uses_python_command(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    CursorHost().install(ctx)
    hooks = json.loads((ctx.target / "hooks.json").read_text())["hooks"]
    sample = hooks["sessionStart"][0]["command"]
    # PYTHON_COMMAND is the first token of every hook command string on both
    # POSIX (shlex.join) and Windows (subprocess.list2cmdline).
    assert sample.split()[0] == PYTHON_COMMAND or sample.split()[0] == f'"{PYTHON_COMMAND}"'


def test_cursor_install_writes_rule_file(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    CursorHost().install(ctx)
    rule = (ctx.target / "rules" / "cq.mdc").read_text()
    assert "alwaysApply: true" in rule


def test_cursor_install_does_not_overwrite_user_rule(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    rule_path = ctx.target / "rules" / "cq.mdc"
    rule_path.parent.mkdir(parents=True)
    rule_path.write_text("user-edited\n")
    CursorHost().install(ctx)
    assert rule_path.read_text() == "user-edited\n"


def test_cursor_install_writes_all_four_hooks(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    shared_runtime = runtime_root()
    CursorHost().install(ctx)
    hooks = json.loads((ctx.target / "hooks.json").read_text())["hooks"]
    assert set(hooks) == {"sessionStart", "postToolUseFailure", "postToolUse", "stop"}
    for entries in hooks.values():
        assert any(str(shared_runtime / RUNTIME_HOOK) in e["command"] for e in entries)


def test_cursor_install_hook_command_includes_state_dir(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    CursorHost().install(ctx)
    hooks = json.loads((ctx.target / "hooks.json").read_text())["hooks"]
    sample = hooks["sessionStart"][0]["command"]
    assert "--state-dir" in sample
    assert str(ctx.target / "cq-hook-state") in sample


def test_cursor_install_idempotent(tmp_path, plugin_root):
    CursorHost().install(_ctx(tmp_path, plugin_root))
    second = CursorHost().install(_ctx(tmp_path, plugin_root))
    assert any(r.action == Action.UNCHANGED for r in second)


def test_cursor_install_shared_skills(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    CursorHost().install(ctx)
    assert (ctx.shared_skills_path / "cq" / "SKILL.md").exists()


def test_cursor_uninstall_removes_assets(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    shared_runtime = runtime_root()
    CursorHost().install(ctx)
    CursorHost().uninstall(ctx)
    config_path = ctx.target / "mcp.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        assert "mcpServers" not in config or "cq" not in config.get("mcpServers", {})
    hooks_path = ctx.target / "hooks.json"
    if hooks_path.exists():
        hooks = json.loads(hooks_path.read_text())["hooks"]
        for entries in hooks.values():
            assert not any("cq_cursor_hook.py" in e["command"] for e in entries)
    assert (shared_runtime / RUNTIME_HOOK).exists()
