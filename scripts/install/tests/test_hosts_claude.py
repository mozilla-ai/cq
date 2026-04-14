"""Tests for the Claude Code marketplace wrapper host."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from cq_install.context import Action, InstallContext, RunState
from cq_install.hosts.claude import (
    CLAUDE_MARKETPLACE_ID,
    CLAUDE_MARKETPLACE_SOURCE_SLUG,
    ClaudeHost,
)


def _ctx(tmp_path: Path, plugin_root: Path, *, dry_run: bool = False) -> InstallContext:
    return InstallContext(
        target=Path("/dev/null"),
        plugin_root=plugin_root,
        shared_skills_path=tmp_path / "shared",
        host_isolated_skills=False,
        dry_run=dry_run,
        run_state=RunState(),
    )


def test_claude_install_runs_marketplace_install(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    with (
        patch("cq_install.hosts.claude.shutil.which", return_value="/usr/bin/claude"),
        patch("cq_install.hosts.claude.subprocess.run") as run,
    ):
        run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        results = ClaudeHost().install(ctx)
    assert [call.args[0] for call in run.call_args_list] == [
        ["claude", "plugin", "marketplace", "add", CLAUDE_MARKETPLACE_SOURCE_SLUG],
        ["claude", "plugin", "install", CLAUDE_MARKETPLACE_ID],
    ]
    assert results[0].action == Action.CREATED


def test_claude_install_dry_run_does_not_invoke_subprocess(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root, dry_run=True)
    with (
        patch("cq_install.hosts.claude.shutil.which", return_value=None),
        patch("cq_install.hosts.claude.subprocess.run") as run,
    ):
        results = ClaudeHost().install(ctx)
    run.assert_not_called()
    assert results[0].action == Action.CREATED


def test_claude_install_missing_cli_raises_clear_error(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    with (
        patch("cq_install.hosts.claude.shutil.which", return_value=None),
        pytest.raises(RuntimeError, match="claude.*PATH"),
    ):
        ClaudeHost().install(ctx)


def test_claude_uninstall_runs_marketplace_remove(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    with (
        patch("cq_install.hosts.claude.shutil.which", return_value="/usr/bin/claude"),
        patch("cq_install.hosts.claude.subprocess.run") as run,
    ):
        run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        results = ClaudeHost().uninstall(ctx)
    assert [call.args[0] for call in run.call_args_list] == [
        ["claude", "plugin", "marketplace", "remove", CLAUDE_MARKETPLACE_ID],
    ]
    assert results[0].action == Action.REMOVED


def test_claude_install_surfaces_returncode_and_stderr_on_failure(tmp_path, plugin_root):
    ctx = _ctx(tmp_path, plugin_root)
    failure = subprocess.CompletedProcess(
        args=["claude", "plugin", "marketplace", "add", CLAUDE_MARKETPLACE_SOURCE_SLUG],
        returncode=3,
        stdout="",
        stderr="error: marketplace not found\n",
    )
    with (
        patch("cq_install.hosts.claude.shutil.which", return_value="/usr/bin/claude"),
        patch("cq_install.hosts.claude.subprocess.run", return_value=failure),
        pytest.raises(RuntimeError) as exc_info,
    ):
        ClaudeHost().install(ctx)

    message = str(exc_info.value)
    assert "3" in message
    assert "marketplace not found" in message
