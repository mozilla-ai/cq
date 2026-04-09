"""Tests for context.py: ChangeResult, Action, InstallContext, RunState."""

from __future__ import annotations

from pathlib import Path

import pytest

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

    ctx = InstallContext(
        target=tmp_path / "target",
        plugin_root=plugin_root,
        shared_skills_path=tmp_path / "shared",
        host_isolated_skills=False,
        dry_run=False,
        run_state=RunState(),
    )
    assert ctx.target == tmp_path / "target"
    assert ctx.plugin_root == plugin_root
    assert ctx.host_isolated_skills is False


def test_run_state_dedup_records_steps_once():
    state = RunState()
    assert state.mark_done("shared-skills", Path("/tmp/a")) is True
    assert state.mark_done("shared-skills", Path("/tmp/a")) is False
    assert state.mark_done("shared-skills", Path("/tmp/b")) is True


def test_ensure_cq_binary_runs_once_per_run_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plugin_root = tmp_path / "plugins" / "cq"
    (plugin_root / "scripts").mkdir(parents=True)
    (plugin_root / "scripts" / "cq_binary.py").touch()
    (plugin_root / "scripts" / "bootstrap.json").write_text('{"cli_version": "0.2.0"}\n')

    calls: list[Path] = []
    sample_result = ChangeResult(action=Action.CREATED, path=tmp_path / "cq", detail="cq v0.2.0")

    def _fake(plugin_root_arg: Path, *, dry_run: bool = False) -> list[ChangeResult]:
        del dry_run
        calls.append(plugin_root_arg)
        return [sample_result]

    monkeypatch.setattr("cq_install.binary.ensure_cq_binary", _fake)

    state = RunState()
    ctx = InstallContext(
        target=tmp_path / "target",
        plugin_root=plugin_root,
        shared_skills_path=tmp_path / "shared",
        host_isolated_skills=False,
        dry_run=False,
        run_state=state,
    )

    first = state.ensure_cq_binary(ctx)
    second = state.ensure_cq_binary(ctx)

    assert first == [sample_result]
    assert second == [sample_result]
    assert len(calls) == 1
    assert calls[0] == plugin_root


def test_ensure_shared_skills_runs_once_per_target(tmp_path: Path):
    plugin_root = tmp_path / "plugins" / "cq"
    (plugin_root / "skills" / "cq").mkdir(parents=True)
    (plugin_root / "skills" / "cq" / "SKILL.md").write_text("# cq\n")

    shared = tmp_path / "shared"
    state = RunState()
    ctx = InstallContext(
        target=tmp_path / "target",
        plugin_root=plugin_root,
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
