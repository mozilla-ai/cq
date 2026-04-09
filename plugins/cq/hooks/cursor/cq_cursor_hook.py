#!/usr/bin/env python3
"""Cursor lifecycle hook for cq.

Invoked once per lifecycle event by Cursor. Stdlib-only because the
host has no Python venv guarantees at this point.

Modes (passed via --mode):
  session-start         Initialize per-session state and sweep old state files.
  post-tool-use         Per-tool observer. Currently a no-op placeholder.
  post-tool-use-failure Capture failed tool calls into per-session state.
  stop                  Emit a summary of any captured failures, then clear state.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

MAX_SNIPPET_LEN = 200
STATE_TTL_SECONDS = 24 * 60 * 60


def main() -> int:
    """Parse args, read the stdin payload, and dispatch to the per-mode handler."""
    args = _parse_args()
    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = _read_payload()

    if args.mode == "session-start":
        return run_session_start(state_dir, payload)
    if args.mode == "post-tool-use":
        return run_post_tool_use(state_dir, payload)
    if args.mode == "post-tool-use-failure":
        return run_post_tool_use_failure(state_dir, payload)
    if args.mode == "stop":
        return run_stop(state_dir, payload)
    print(f"unknown mode: {args.mode}", file=sys.stderr)
    return 2


def run_post_tool_use(state_dir: Path, payload: dict) -> int:
    """Cursor hook docs: https://cursor.com/docs/agent/hooks#post-tool-use."""
    return 0


def run_post_tool_use_failure(state_dir: Path, payload: dict) -> int:
    """Cursor hook docs: https://cursor.com/docs/agent/hooks#post-tool-use-failure."""
    if payload.get("isInterrupt"):
        return 0
    session_id = payload.get("sessionId", "unknown")
    record = {
        "sessionId": session_id,
        "toolName": payload.get("toolName"),
        "input": _format_tool_input(payload.get("toolName", ""), payload.get("toolInput", {})),
        "error": _truncate(str(payload.get("error", "")), MAX_SNIPPET_LEN),
    }
    path = state_dir / f"{session_id}-failure.json"
    path.write_text(json.dumps(record))
    return 0


def run_session_start(state_dir: Path, payload: dict) -> int:
    """Cursor hook docs: https://cursor.com/docs/agent/hooks#session-start."""
    _sweep_old_state(state_dir)
    session_id = payload.get("sessionId", "unknown")
    state_path = state_dir / f"{session_id}-init.json"
    state_path.write_text(json.dumps({"startedAt": int(time.time())}))
    return 0


def run_stop(state_dir: Path, payload: dict) -> int:
    """Cursor hook docs: https://cursor.com/docs/agent/hooks#stop."""
    session_id = payload.get("sessionId", "unknown")
    failure_path = state_dir / f"{session_id}-failure.json"
    if failure_path.exists():
        record = json.loads(failure_path.read_text())
        print(
            f"cq: previous tool {record.get('toolName')} failed: {record.get('error')}\n  input: {record.get('input')}"
        )
        failure_path.unlink()
    init_path = state_dir / f"{session_id}-init.json"
    if init_path.exists():
        init_path.unlink()
    return 0


def _format_tool_input(tool_name: str, tool_input: dict) -> str:
    if tool_name in {"Shell", "Bash"}:
        return _truncate(str(tool_input.get("command", "")), MAX_SNIPPET_LEN)
    if tool_name == "Edit":
        return _truncate(str(tool_input.get("file_path", "")), MAX_SNIPPET_LEN)
    if tool_name == "Write":
        path = tool_input.get("path") or tool_input.get("file_path", "")
        snippet = tool_input.get("content", "")
        return _truncate(f"{path}: {snippet}", MAX_SNIPPET_LEN)
    if tool_name == "Read":
        return _truncate(str(tool_input.get("file_path", "")), MAX_SNIPPET_LEN)
    return _truncate(f"{tool_name}({tool_input!r})", MAX_SNIPPET_LEN)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="cq_cursor_hook")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state-dir", required=True)
    return parser.parse_args()


def _read_payload() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _sweep_old_state(state_dir: Path) -> None:
    cutoff = time.time() - STATE_TTL_SECONDS
    for entry in state_dir.iterdir():
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                entry.unlink()
        except OSError:
            continue


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "…"


if __name__ == "__main__":
    raise SystemExit(main())
