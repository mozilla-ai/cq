#!/usr/bin/env python3
"""Bootstrap the cq MCP server for the Claude plugin.

Ensures the cq binary is available at the shared runtime cache path,
then replaces this process with `cq mcp` so Claude talks directly to
the Go MCP server over stdio.

The binary fetch, version, and cache logic live in the sibling
`cq_binary.py` module; this script is a thin Claude-facing launcher.
Claude runs it via `python ${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap.py`,
which puts the script's directory on `sys.path`, so the bare
`import cq_binary` resolves to the sibling file.
"""

import os
import sys
from pathlib import Path

import cq_binary


def main() -> None:
    """Ensure the cq binary is cached, then exec into the MCP server."""
    metadata_path = Path(__file__).resolve().with_name("bootstrap.json")
    required_version = cq_binary.load_required_version(metadata_path)
    if not required_version:
        print("Error: required CLI version not set in bootstrap metadata", file=sys.stderr)
        sys.exit(1)

    bin_dir = cq_binary.shared_bin_dir()
    binary = bin_dir / cq_binary.cq_binary_name()

    cq_binary.ensure_binary(binary, required_version, bin_dir)

    os.execvp(str(binary), [str(binary), "mcp"])


if __name__ == "__main__":
    main()
