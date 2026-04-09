"""Shared content blobs the installer writes into target files.

Host-specific content (e.g. the Cursor rule file body) lives alongside
the host adapter that uses it, not here. This module is strictly for
content that is shared across two or more hosts.
"""

from __future__ import annotations

import platform

CQ_BLOCK_START = "<!-- cq:start -->"
CQ_BLOCK_END = "<!-- cq:end -->"

CQ_RUNTIME_MANIFEST = ".cq-install-runtime-manifest.json"

# The key name every host uses for the cq MCP server entry.
# Wrapping differs by host: OpenCode uses `.mcp.cq`, Cursor / Windsurf use
# `.mcpServers.cq`. Only the leaf key is shared.
CQ_MCP_KEY = "cq"

CQ_AGENTS_BLOCK = f"""{CQ_BLOCK_START}
## CQ

Before starting any implementation task, load the `cq` skill and follow its Core Protocol.
{CQ_BLOCK_END}"""

# Canonical Python command name written into every host's MCP config.
# POSIX uses `python3`; Windows uses `python` per python.org docs which say
# `python3` on Windows is a compatibility stub "not meant to be widely used
# or recommended". Written as a literal name (not an absolute path) so it
# PATH-resolves at the host's invocation time; this avoids baking the
# installer's own venv location into long-lived user config.
# Detection matches plugins/cq/scripts/cq_binary.py's `platform.system()` idiom.
PYTHON_COMMAND = "python" if platform.system() == "Windows" else "python3"


def cq_binary_name() -> str:
    """Return the cq binary name for the current platform.

    Returns 'cq.exe' on Windows, 'cq' on other platforms.
    """
    return "cq.exe" if platform.system() == "Windows" else "cq"
