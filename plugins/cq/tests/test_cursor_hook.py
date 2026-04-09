"""Tests for plugins/cq/hooks/cursor/cq_cursor_hook.py."""

from __future__ import annotations

import json
import os
import sys
import time
from io import StringIO


def _stdin_with(payload: dict) -> StringIO:
    return StringIO(json.dumps(payload))


def test_truncate_short_string_unchanged(hook):
    assert hook._truncate("hello", 10) == "hello"


def test_truncate_long_string_appends_ellipsis(hook):
    out = hook._truncate("a" * 100, 10)
    assert out.startswith("aaaaaaaaaa")
    assert out.endswith("…")
    assert len(out) == 11  # 10 + single ellipsis char


def test_format_tool_input_shell_extracts_command(hook):
    out = hook._format_tool_input("Shell", {"command": "ls -la"})
    assert "ls -la" in out


def test_format_tool_input_edit_extracts_file_path(hook):
    out = hook._format_tool_input("Edit", {"file_path": "/x/file.py"})
    assert "/x/file.py" in out


def test_format_tool_input_write_extracts_path_and_content(hook):
    out = hook._format_tool_input("Write", {"path": "/x/y", "content": "body"})
    assert "/x/y" in out


def test_format_tool_input_bash_extracts_command(hook):
    out = hook._format_tool_input("Bash", {"command": "echo hi"})
    assert "echo hi" in out


def test_format_tool_input_read_extracts_file_path(hook):
    out = hook._format_tool_input("Read", {"file_path": "/x/y.md"})
    assert "/x/y.md" in out


def test_format_tool_input_unknown_returns_repr(hook):
    out = hook._format_tool_input("MysteryTool", {"k": "v"})
    assert "MysteryTool" in out


def test_run_session_start_creates_state_file(hook, tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    monkeypatch.setattr(
        sys,
        "argv",
        ["cq_cursor_hook.py", "--mode", "session-start", "--state-dir", str(state_dir)],
    )
    monkeypatch.setattr("sys.stdin", _stdin_with({"sessionId": "abc"}))
    hook.main()
    files = list(state_dir.iterdir())
    assert len(files) == 1
    assert files[0].name.startswith("abc")


def test_run_session_start_sweeps_old_state(hook, tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    old = state_dir / "old.json"
    old.write_text("{}")
    old_mtime = time.time() - 60 * 60 * 25  # 25 hours ago
    os.utime(old, (old_mtime, old_mtime))

    monkeypatch.setattr(
        sys,
        "argv",
        ["cq_cursor_hook.py", "--mode", "session-start", "--state-dir", str(state_dir)],
    )
    monkeypatch.setattr("sys.stdin", _stdin_with({"sessionId": "new"}))
    hook.main()
    assert not old.exists()


def test_run_post_tool_use_failure_writes_state(hook, tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        ["cq_cursor_hook.py", "--mode", "post-tool-use-failure", "--state-dir", str(state_dir)],
    )
    monkeypatch.setattr(
        "sys.stdin",
        _stdin_with(
            {
                "sessionId": "s1",
                "toolName": "Edit",
                "toolInput": {"file_path": "/x/y"},
                "error": "boom",
            }
        ),
    )
    hook.main()
    files = list(state_dir.iterdir())
    assert any("s1" in f.name for f in files)


def test_run_post_tool_use_failure_skips_when_interrupt(hook, tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        ["cq_cursor_hook.py", "--mode", "post-tool-use-failure", "--state-dir", str(state_dir)],
    )
    monkeypatch.setattr(
        "sys.stdin",
        _stdin_with(
            {
                "sessionId": "s1",
                "toolName": "Shell",
                "isInterrupt": True,
                "error": "interrupted",
            }
        ),
    )
    hook.main()
    assert not any(state_dir.iterdir())


def test_run_stop_with_failure_state_emits_summary(hook, tmp_path, monkeypatch, capsys):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "s1-failure.json").write_text(json.dumps({"sessionId": "s1", "toolName": "Edit", "error": "boom"}))
    monkeypatch.setattr(
        sys,
        "argv",
        ["cq_cursor_hook.py", "--mode", "stop", "--state-dir", str(state_dir)],
    )
    monkeypatch.setattr("sys.stdin", _stdin_with({"sessionId": "s1"}))
    hook.main()
    out = capsys.readouterr().out
    assert "boom" in out
    assert not (state_dir / "s1-failure.json").exists()


def test_run_stop_without_failure_state_is_quiet(hook, tmp_path, monkeypatch, capsys):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        ["cq_cursor_hook.py", "--mode", "stop", "--state-dir", str(state_dir)],
    )
    monkeypatch.setattr("sys.stdin", _stdin_with({"sessionId": "s1"}))
    hook.main()
    captured = capsys.readouterr()
    assert "boom" not in captured.out
