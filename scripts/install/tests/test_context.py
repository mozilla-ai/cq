"""Tests for context.py: ChangeResult, Action, InstallContext, RunState."""

from __future__ import annotations

from pathlib import Path

from cq_install.context import Action, ChangeResult, InstallContext, RunState


def test_action_values_match_spec():
    assert Action.CREATED.value == "created"
    assert Action.UPDATED.value == "updated"
    assert Action.UNCHANGED.value == "unchanged"
    assert Action.REMOVED.value == "removed"
    assert Action.SKIPPED.value == "skipped"


def test_change_result_is_frozen():
    result = ChangeResult(action=Action.CREATED, path=Path("/tmp/x"), detail="ok")
    try:
        result.action = Action.REMOVED  # type: ignore[misc]
    except (AttributeError, TypeError):
        return
    raise AssertionError("ChangeResult should be frozen")


def test_change_result_default_detail():
    result = ChangeResult(action=Action.UNCHANGED, path=Path("/tmp/y"))
    assert result.detail == ""


def test_install_context_construction(tmp_path: Path):
    plugin_root = tmp_path / "plugins" / "cq"
    plugin_root.mkdir(parents=True)
    bootstrap = plugin_root / "scripts" / "bootstrap.py"
    bootstrap.parent.mkdir()
    bootstrap.touch()

    ctx = InstallContext(
        target=tmp_path / "target",
        plugin_root=plugin_root,
        bootstrap_path=bootstrap,
        shared_skills_path=tmp_path / "shared",
        host_isolated_skills=False,
        dry_run=False,
        run_state=RunState(),
    )
    assert ctx.target == tmp_path / "target"
    assert ctx.bootstrap_path == bootstrap
    assert ctx.host_isolated_skills is False


def test_run_state_dedup_records_steps_once():
    state = RunState()
    assert state.mark_done("shared-skills", Path("/tmp/a")) is True
    assert state.mark_done("shared-skills", Path("/tmp/a")) is False
    assert state.mark_done("shared-skills", Path("/tmp/b")) is True


def test_ensure_shared_skills_runs_once_per_target(tmp_path: Path):
    plugin_root = tmp_path / "plugins" / "cq"
    (plugin_root / "skills" / "cq").mkdir(parents=True)
    (plugin_root / "skills" / "cq" / "SKILL.md").write_text("# cq\n")
    bootstrap = plugin_root / "scripts" / "bootstrap.py"
    bootstrap.parent.mkdir()
    bootstrap.touch()

    shared = tmp_path / "shared"
    state = RunState()
    ctx = InstallContext(
        target=tmp_path / "target",
        plugin_root=plugin_root,
        bootstrap_path=bootstrap,
        shared_skills_path=shared,
        host_isolated_skills=False,
        dry_run=False,
        run_state=state,
    )

    first = state.ensure_shared_skills(ctx)
    second = state.ensure_shared_skills(ctx)

    assert len(first) == 1
    assert second == []  # already done; second invocation is a no-op.
    assert (shared / "cq" / "SKILL.md").exists()
