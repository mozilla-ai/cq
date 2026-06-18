#!/usr/bin/env python3
"""Bootstrap the cq MCP server for the Copilot plugin.

Ensures the cq binary is available at the shared runtime cache path,
then replaces this process with `cq mcp` so Copilot talks directly to
the Go MCP server over stdio.

The binary fetch, version, and cache logic live in the sibling
`cq_binary.py` module; this script is a thin launcher.
"""

import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path


def _log_path() -> Path:
    """Return the path to the bootstrap diagnostic log file."""
    log_dir = Path(os.environ.get("TEMP", Path.home() / "AppData" / "Local" / "Temp"))
    return log_dir / "cq-bootstrap.log"


def _log(msg: str) -> None:
    """Append a timestamped message to the diagnostic log."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with open(_log_path(), "a", encoding="utf-8") as f:
            f.write(f"{ts} {msg}\n")
    except OSError:
        pass


_LOG_HEADER = "=" * 60


def _log_env() -> None:
    """Log key environment details for diagnostics."""
    _log(_LOG_HEADER)
    _log(f"python  : {sys.executable} (v{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro})")
    _log(f"argv    : {sys.argv}")
    _log(f"cwd     : {Path.cwd()}")
    _log(f"__file__: {__file__}")
    _log(f"resolved: {Path(__file__).resolve()}")
    _log(f"sys.path[0]: {sys.path[0]}")
    for var in ("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "PATH", "TEMP", "TMP", "HOME", "USERPROFILE"):
        _log(f"env {var}: {os.environ.get(var, '<unset>')}")


def main() -> None:
    """Ensure the cq binary is cached, then exec into the MCP server."""
    try:
        _log_env()

        import cq_binary
        _log("import cq_binary: OK")
    except Exception:
        _log(f"import cq_binary FAILED:\n{traceback.format_exc()}")
        raise

    try:
        metadata_path = Path(__file__).resolve().with_name("bootstrap.json")
        _log(f"metadata_path: {metadata_path} (exists={metadata_path.exists()})")
        min_version = cq_binary.load_min_version(metadata_path)
        _log(f"min_version: {min_version!r}")
        if not min_version:
            _log("FATAL: min_version is empty")
            print("Error: minimum CLI version not set in bootstrap metadata", file=sys.stderr)
            sys.exit(1)
    except Exception:
        _log(f"metadata load FAILED:\n{traceback.format_exc()}")
        raise

    try:
        bin_dir = cq_binary.shared_bin_dir()
        _log(f"bin_dir: {bin_dir}")
        binary = bin_dir / cq_binary.cq_binary_name()
        _log(f"binary: {binary}")

        cq_binary.ensure_binary(binary, min_version, bin_dir)
        _log(f"ensure_binary done, binary exists={binary.is_file()}")
    except Exception:
        _log(f"ensure_binary FAILED:\n{traceback.format_exc()}")
        raise

    try:
        _log(f"execvp: {binary} mcp")
        import subprocess
        try:
            process = subprocess.Popen([str(binary), "mcp"])
            process.wait()
            sys.exit(process.returncode)
        except KeyboardInterrupt:
            process.terminate()
            sys.exit(130)
        # subprocess wait blocks until completion
        _log("execvp RETURNED (should not happen)")
    except Exception:
        _log(f"execvp FAILED:\n{traceback.format_exc()}")
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _log(f"UNHANDLED exception:\n{traceback.format_exc()}")
        sys.exit(1)
