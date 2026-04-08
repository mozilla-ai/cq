"""Shared content blobs the installer writes into target files.

Host-specific content (e.g. the Cursor rule file body) lives alongside
the host adapter that uses it, not here. This module is strictly for
content that is shared across two or more hosts.
"""

from __future__ import annotations

CQ_BLOCK_START = "<!-- cq:start -->"
CQ_BLOCK_END = "<!-- cq:end -->"

CQ_AGENTS_BLOCK = f"""{CQ_BLOCK_START}
## CQ

Before starting any implementation task, load the `cq` skill and follow its Core Protocol.
{CQ_BLOCK_END}"""
