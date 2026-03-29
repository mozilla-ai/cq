#!/usr/bin/env python3
"""Cursor hook helpers for cq.

This script uses only the Python standard library so it can run before the
cq MCP server environment has been synced.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

STATE_FILE_ENV = "CQ_CURSOR_CQ_STATE_FILE"
STATE_DIR_NAME = "cq-hook-state"
MAX_SNIPPET_LEN = 240


def _read_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    return json.loads(raw)


def _write_response(payload: dict[str, Any]) -> int:
    sys.stdout.write(json.dumps(payload) + "\n")
    return 0


def _state_file() -> Path | None:
    raw_path = os.environ.get(STATE_FILE_ENV, "").strip()
    if not raw_path:
        return None
    return Path(raw_path)


def _load_state(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def _save_state(path: Path | None, state: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def _clear_state(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _truncate(value: Any) -> str:
    text = str(value).strip()
    if len(text) <= MAX_SNIPPET_LEN:
        return text
    return text[: MAX_SNIPPET_LEN - 3] + "..."


def _format_tool_input(tool_name: str, tool_input: Any) -> str:
    if not isinstance(tool_input, dict):
        return ""
    if tool_name == "Shell":
        command = tool_input.get("command", "")
        if command:
            return f" command=`{_truncate(command)}`"
    return ""


def run_session_start(server_dir: str, uv_bin: str) -> int:
    payload = _read_payload()
    session_id = str(payload.get("session_id", "")).strip()
    if not session_id:
        return _write_response({})

    state_dir = Path.home() / ".cursor" / STATE_DIR_NAME
    state_file = state_dir / f"{session_id}.json"
    _clear_state(state_file)

    response: dict[str, Any] = {
        "env": {
            STATE_FILE_ENV: str(state_file),
        }
    }

    proc = subprocess.run(
        [uv_bin, "sync", "--directory", server_dir, "--quiet"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = _truncate(proc.stderr or proc.stdout or "unknown error")
        response["additional_context"] = (
            "cq Cursor session setup could not sync the cq MCP server "
            f"environment. Command: `{uv_bin} sync --directory {server_dir} "
            f"--quiet`. Error: {stderr}"
        )

    return _write_response(response)


def run_post_tool_use() -> int:
    _read_payload()
    _clear_state(_state_file())
    return _write_response({})


def run_post_tool_use_failure() -> int:
    payload = _read_payload()
    if payload.get("is_interrupt"):
        return _write_response({})

    tool_name = str(payload.get("tool_name", "")).strip()
    if tool_name == "MCP: cq":
        return _write_response({})

    state = {
        "tool_name": tool_name,
        "failure_type": str(payload.get("failure_type", "")).strip(),
        "error_message": _truncate(payload.get("error_message", "")),
        "cwd": _truncate(payload.get("cwd", "")),
        "tool_context": _format_tool_input(tool_name, payload.get("tool_input")),
    }
    _save_state(_state_file(), state)
    return _write_response({})


def run_stop() -> int:
    payload = _read_payload()
    if payload.get("status") != "error" or payload.get("loop_count", 0) != 0:
        _clear_state(_state_file())
        return _write_response({})

    state = _load_state(_state_file())
    _clear_state(_state_file())
    if not state:
        return _write_response({})

    tool_name = state.get("tool_name") or "unknown"
    failure_type = state.get("failure_type") or "error"
    error_message = state.get("error_message") or "unknown error"
    cwd = state.get("cwd")
    tool_context = state.get("tool_context", "")

    location = f" cwd=`{cwd}`" if cwd else ""
    followup = (
        "A tool just failed and the agent loop ended. Before retrying, load "
        "the `cq` skill if it is available and query `cq` using domain tags "
        "derived from this failure context instead of retrying blindly. "
        f"Recent failure: tool=`{tool_name}` type=`{failure_type}`"
        f"{tool_context}{location} error=`{error_message}`."
    )
    return _write_response({"followup_message": followup})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        required=True,
        choices=("session-start", "post-tool-use", "post-tool-use-failure", "stop"),
    )
    parser.add_argument("--server-dir", default="")
    parser.add_argument("--uv-bin", default="uv")
    args = parser.parse_args()

    if args.mode == "session-start":
        return run_session_start(args.server_dir, args.uv_bin)
    if args.mode == "post-tool-use":
        return run_post_tool_use()
    if args.mode == "post-tool-use-failure":
        return run_post_tool_use_failure()
    return run_stop()


if __name__ == "__main__":
    raise SystemExit(main())
