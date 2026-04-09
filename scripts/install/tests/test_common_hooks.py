"""Tests for hook entry primitives in common.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cq_install.common import remove_hook_entry, upsert_hook_entry
from cq_install.context import Action


def test_upsert_creates_hook_file_with_entry(tmp_path: Path):
    target = tmp_path / "hooks.json"
    result = upsert_hook_entry(
        target,
        hook_name="sessionStart",
        command="python3 /x/cq_cursor_hook.py --mode session-start",
        dry_run=False,
    )
    assert result.action == Action.CREATED
    data = json.loads(target.read_text())
    assert data["hooks"]["sessionStart"][0]["command"] == ("python3 /x/cq_cursor_hook.py --mode session-start")


def test_upsert_idempotent_when_command_present(tmp_path: Path):
    target = tmp_path / "hooks.json"
    cmd = "python3 /x/cq_cursor_hook.py --mode stop"
    upsert_hook_entry(target, hook_name="stop", command=cmd, dry_run=False)
    result = upsert_hook_entry(target, hook_name="stop", command=cmd, dry_run=False)
    assert result.action == Action.UNCHANGED


def test_upsert_preserves_other_hook_entries(tmp_path: Path):
    target = tmp_path / "hooks.json"
    target.write_text(json.dumps({"hooks": {"sessionStart": [{"command": "user-script"}]}}))
    upsert_hook_entry(
        target,
        hook_name="sessionStart",
        command="python3 /x/cq_cursor_hook.py --mode session-start",
        dry_run=False,
    )
    data = json.loads(target.read_text())
    commands = [entry["command"] for entry in data["hooks"]["sessionStart"]]
    assert "user-script" in commands
    assert any("cq_cursor_hook.py" in c for c in commands)


def test_upsert_legacy_commands_are_removed_first(tmp_path: Path):
    target = tmp_path / "hooks.json"
    target.write_text(json.dumps({"hooks": {"stop": [{"command": "python3 /old/legacy.py --stop"}]}}))
    result = upsert_hook_entry(
        target,
        hook_name="stop",
        command="python3 /new/cq_cursor_hook.py --mode stop",
        legacy_commands=["python3 /old/legacy.py --stop"],
        dry_run=False,
    )
    assert result.action == Action.UPDATED
    commands = [entry["command"] for entry in json.loads(target.read_text())["hooks"]["stop"]]
    assert "python3 /old/legacy.py --stop" not in commands
    assert "python3 /new/cq_cursor_hook.py --mode stop" in commands


def test_upsert_extra_fields_are_set_on_entry(tmp_path: Path):
    target = tmp_path / "hooks.json"
    upsert_hook_entry(
        target,
        hook_name="postToolUse",
        command="python3 /x/h.py --mode post-tool-use",
        extra_fields={"matcher": "Edit"},
        dry_run=False,
    )
    entry = json.loads(target.read_text())["hooks"]["postToolUse"][0]
    assert entry["matcher"] == "Edit"


def test_upsert_dry_run_does_not_write(tmp_path: Path):
    target = tmp_path / "hooks.json"
    result = upsert_hook_entry(
        target,
        hook_name="sessionStart",
        command="python3 /x/h.py --mode session-start",
        dry_run=True,
    )
    assert result.action == Action.CREATED
    assert not target.exists()


def test_remove_hook_entry_deletes_only_matching_command(tmp_path: Path):
    target = tmp_path / "hooks.json"
    target.write_text(
        json.dumps(
            {
                "hooks": {
                    "stop": [
                        {"command": "user-script"},
                        {"command": "python3 /x/cq_cursor_hook.py --mode stop"},
                    ]
                }
            }
        )
    )
    result = remove_hook_entry(
        target,
        hook_name="stop",
        command="python3 /x/cq_cursor_hook.py --mode stop",
        dry_run=False,
    )
    assert result.action == Action.REMOVED
    commands = [entry["command"] for entry in json.loads(target.read_text())["hooks"]["stop"]]
    assert commands == ["user-script"]


def test_remove_hook_entry_prunes_empty_hook_list(tmp_path: Path):
    target = tmp_path / "hooks.json"
    target.write_text(json.dumps({"hooks": {"stop": [{"command": "python3 /x/h.py --mode stop"}]}}))
    remove_hook_entry(
        target,
        hook_name="stop",
        command="python3 /x/h.py --mode stop",
        dry_run=False,
    )
    data = json.loads(target.read_text())
    assert "stop" not in data["hooks"]


def test_upsert_hook_raises_when_top_level_is_not_object(tmp_path: Path):
    target = tmp_path / "hooks.json"
    target.write_text(json.dumps(["not", "an", "object"]))
    with pytest.raises(ValueError) as exc_info:
        upsert_hook_entry(
            target,
            hook_name="sessionStart",
            command="python3 /x/h.py",
            dry_run=False,
        )
    assert str(target) in str(exc_info.value)


def test_upsert_hook_raises_when_hooks_is_not_object(tmp_path: Path):
    target = tmp_path / "hooks.json"
    target.write_text(json.dumps({"hooks": ["not", "an", "object"]}))
    with pytest.raises(ValueError) as exc_info:
        upsert_hook_entry(
            target,
            hook_name="sessionStart",
            command="python3 /x/h.py",
            dry_run=False,
        )
    assert str(target) in str(exc_info.value)
    assert "hooks" in str(exc_info.value)


def test_upsert_hook_raises_when_hook_entries_is_not_list(tmp_path: Path):
    target = tmp_path / "hooks.json"
    target.write_text(json.dumps({"hooks": {"sessionStart": {"not": "a list"}}}))
    with pytest.raises(ValueError) as exc_info:
        upsert_hook_entry(
            target,
            hook_name="sessionStart",
            command="python3 /x/h.py",
            dry_run=False,
        )
    assert str(target) in str(exc_info.value)
    assert "sessionStart" in str(exc_info.value)


def test_remove_hook_entry_skips_when_top_level_not_object(tmp_path: Path):
    target = tmp_path / "hooks.json"
    target.write_text(json.dumps(["not", "an", "object"]))
    result = remove_hook_entry(
        target,
        hook_name="stop",
        command="python3 /x/h.py --mode stop",
        dry_run=False,
    )
    assert result.action == Action.SKIPPED
    assert str(target) in result.detail


def test_remove_hook_entry_skips_when_hooks_not_object(tmp_path: Path):
    target = tmp_path / "hooks.json"
    target.write_text(json.dumps({"hooks": "not-a-dict"}))
    result = remove_hook_entry(
        target,
        hook_name="stop",
        command="python3 /x/h.py --mode stop",
        dry_run=False,
    )
    assert result.action == Action.SKIPPED
