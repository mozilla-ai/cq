"""Tests for the Pi host install/uninstall flow."""

from __future__ import annotations

from pathlib import Path

from cq_install.content import cq_binary_name
from cq_install.context import Action, InstallContext, RunState
from cq_install.hosts.pi import PiHost
from cq_install.runtime import runtime_root

RUNTIME_BINARY = Path("bin") / cq_binary_name()


def _ctx(tmp_path: Path, plugin_root: Path, *, host_isolated: bool = False) -> InstallContext:
    target = tmp_path / "target"
    target.mkdir(exist_ok=True)
    return InstallContext(
        target=target,
        plugin_root=plugin_root,
        shared_skills_path=tmp_path / "shared",
        host_isolated_skills=host_isolated,
        dry_run=False,
        run_state=RunState(),
    )


def test_pi_global_target_default():
    assert PiHost().global_target() == Path.home() / ".pi" / "agent"


def test_pi_project_target():
    assert PiHost().project_target(Path("/proj")) == Path("/proj") / ".pi"


def test_pi_install_shared_skills_default(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root, host_isolated=False)
    PiHost().install(ctx)
    assert (ctx.shared_skills_path / "cq" / "SKILL.md").exists()
    assert not (ctx.target / "skills").exists()


def test_pi_install_host_isolated_copies_skills_into_target(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root, host_isolated=True)
    PiHost().install(ctx)
    assert (ctx.target / "skills" / "cq" / "SKILL.md").exists()


def test_pi_install_writes_agents_block_with_cli_mapping(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    PiHost().install(ctx)

    text = (ctx.target / "AGENTS.md").read_text()
    assert "<!-- cq:start -->" in text
    assert "<!-- cq:end -->" in text
    # Absolute binary path is embedded (do not assume cq is on PATH).
    assert str(runtime_root() / RUNTIME_BINARY) in text
    # All five verbs are mapped to the CLI.
    for verb in ("query", "propose", "confirm", "flag", "status"):
        assert f"{verb} " in text
    assert "--format json" in text


def test_pi_install_agents_block_idempotent(tmp_path, plugin_root):
    PiHost().install(_ctx(tmp_path, plugin_root))
    first = (tmp_path / "target" / "AGENTS.md").read_text()
    PiHost().install(_ctx(tmp_path, plugin_root))
    assert (tmp_path / "target" / "AGENTS.md").read_text() == first


def test_pi_install_writes_prefixed_prompt_files(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    PiHost().install(ctx)
    prompts = ctx.target / "prompts"
    assert (prompts / "cq-status.md").exists()
    assert (prompts / "cq-reflect.md").exists()
    # name: frontmatter stripped (Pi names commands from the filename).
    assert "name: cq:status" not in (prompts / "cq-status.md").read_text()


def test_pi_install_idempotent(tmp_path, plugin_root):
    PiHost().install(_ctx(tmp_path, plugin_root))
    second = PiHost().install(_ctx(tmp_path, plugin_root))
    actions = [r.action for r in second]
    assert all(a in (Action.UNCHANGED, Action.CREATED) for a in actions)
    assert any(a == Action.UNCHANGED for a in actions)


def test_pi_uninstall_removes_assets(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    PiHost().install(ctx)
    PiHost().uninstall(ctx)
    assert not (ctx.target / "prompts" / "cq-status.md").exists()
    text = (ctx.target / "AGENTS.md").read_text() if (ctx.target / "AGENTS.md").exists() else ""
    assert "<!-- cq:start -->" not in text


def test_pi_uninstall_preserves_user_edited_prompts(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    PiHost().install(ctx)
    prompt_file = ctx.target / "prompts" / "cq-status.md"
    prompt_file.write_text("user-edited content\n")
    PiHost().uninstall(ctx)
    assert prompt_file.exists()
    assert prompt_file.read_text() == "user-edited content\n"
