"""Static content blobs the installer writes into target files."""

from __future__ import annotations

CQ_BLOCK_START = "<!-- cq:start -->"
CQ_BLOCK_END = "<!-- cq:end -->"

CQ_AGENTS_BLOCK = f"""{CQ_BLOCK_START}
## CQ

Before starting any implementation task, load the `cq` skill and follow its Core Protocol.
{CQ_BLOCK_END}"""

CURSOR_RULE_CONTENT = """---
description: cq shared knowledge commons
alwaysApply: true
---

Before starting any implementation task, load the `cq` skill and follow its Core Protocol.
"""
