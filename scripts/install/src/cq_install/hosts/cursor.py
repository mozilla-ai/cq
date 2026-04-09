"""Cursor host adapter."""

from __future__ import annotations

import hashlib
import platform
import shlex
import subprocess
from pathlib import Path

from cq_install.common import (
    copy_selected_paths,
    copy_tree,
    remove_copied_tree,
    remove_hook_entry,
    remove_json_entry,
    remove_owned_file,
    upsert_hook_entry,
    upsert_json_entry,
    write_if_missing,
)
from cq_install.content import (
    CQ_MCP_KEY,
    CQ_RUNTIME_MANIFEST,
    PYTHON_COMMAND,
    cq_binary_name,
)
from cq_install.context import ChangeResult, InstallContext
from cq_install.hosts.base import HostDef
from cq_install.runtime import runtime_root

CURSOR_RULE_CONTENT = """---
description: cq shared knowledge commons
alwaysApply: true
---

Before starting any implementation task, load the `cq` skill and follow its Core Protocol.
"""

CURSOR_HOOK_MODES: list[tuple[str, str]] = [
    ("sessionStart", "session-start"),
    ("postToolUseFailure", "post-tool-use-failure"),
    ("postToolUse", "post-tool-use"),
    ("stop", "stop"),
]

# Populate when the hook command shape changes in a future release.
# Entries matching these strings are removed on install before the desired
# entry is (re)inserted, giving a clean migration path for stale commands.
CURSOR_LEGACY_HOOK_COMMANDS: list[str] = []

CURSOR_HOOKS_FILE = "hooks.json"
CURSOR_HOOK_SCRIPT_RELPATH = Path("hooks") / "cursor" / "cq_cursor_hook.py"
CURSOR_HOST_SKILLS_MANIFEST = ".cq-install-manifest.json"
CURSOR_MCP_FILE = "mcp.json"
CURSOR_MCP_SERVERS_KEY = "mcpServers"
CURSOR_RULE_HASH = hashlib.sha256(CURSOR_RULE_CONTENT.encode()).hexdigest()
CURSOR_RULE_RELPATH = Path("rules") / "cq.mdc"
CURSOR_SKILLS_DIR = "skills"
CURSOR_STATE_DIR = "cq-hook-state"

# Cursor reads its config from ~/.cursor on every platform and from
# <project>/.cursor for per-project installs.
CURSOR_TARGET_DIR = ".cursor"


class CursorHost(HostDef):
    """Adapter for the Cursor editor host."""

    name = "cursor"

    def global_target(self) -> Path:
        """Return the global Cursor config dir."""
        return Path.home() / CURSOR_TARGET_DIR

    def install(self, ctx: InstallContext) -> list[ChangeResult]:
        """Install cq into the Cursor target."""
        results: list[ChangeResult] = []
        results.extend(self._install_skills(ctx))
        results.extend(ctx.run_state.ensure_cq_binary(ctx))
        results.append(self._install_runtime(ctx))
        results.append(self._install_mcp(ctx))
        results.append(
            write_if_missing(
                ctx.target / CURSOR_RULE_RELPATH,
                CURSOR_RULE_CONTENT,
                dry_run=ctx.dry_run,
            )
        )
        results.extend(self._install_hooks(ctx))
        return results

    def project_target(self, project: Path) -> Path:
        """Return the per-project Cursor config dir."""
        return project / CURSOR_TARGET_DIR

    def uninstall(self, ctx: InstallContext) -> list[ChangeResult]:
        """Remove cq from the Cursor target."""
        results: list[ChangeResult] = [
            remove_copied_tree(
                ctx.target / CURSOR_SKILLS_DIR,
                manifest_name=CURSOR_HOST_SKILLS_MANIFEST,
                dry_run=ctx.dry_run,
            ),
            remove_json_entry(
                ctx.target / CURSOR_MCP_FILE,
                [CURSOR_MCP_SERVERS_KEY, CQ_MCP_KEY],
                dry_run=ctx.dry_run,
            ),
            remove_owned_file(
                ctx.target / CURSOR_RULE_RELPATH,
                expected_content_hash=CURSOR_RULE_HASH,
                dry_run=ctx.dry_run,
            ),
        ]
        for hook_name, mode in CURSOR_HOOK_MODES:
            results.append(
                remove_hook_entry(
                    ctx.target / CURSOR_HOOKS_FILE,
                    hook_name=hook_name,
                    command=_hook_command(ctx, mode),
                    dry_run=ctx.dry_run,
                )
            )
        return results

    def _install_hooks(self, ctx: InstallContext) -> list[ChangeResult]:
        results: list[ChangeResult] = []
        for hook_name, mode in CURSOR_HOOK_MODES:
            results.append(
                upsert_hook_entry(
                    ctx.target / CURSOR_HOOKS_FILE,
                    hook_name=hook_name,
                    command=_hook_command(ctx, mode),
                    legacy_commands=CURSOR_LEGACY_HOOK_COMMANDS,
                    dry_run=ctx.dry_run,
                )
            )
        return results

    def _install_mcp(self, ctx: InstallContext) -> ChangeResult:
        binary_path = runtime_root() / "bin" / cq_binary_name()
        return upsert_json_entry(
            ctx.target / CURSOR_MCP_FILE,
            [CURSOR_MCP_SERVERS_KEY, CQ_MCP_KEY],
            {
                "command": str(binary_path),
                "args": ["mcp"],
            },
            dry_run=ctx.dry_run,
        )

    def _install_runtime(self, ctx: InstallContext) -> ChangeResult:
        return copy_selected_paths(
            ctx.plugin_root,
            runtime_root(),
            relpaths=[CURSOR_HOOK_SCRIPT_RELPATH],
            manifest_name=CQ_RUNTIME_MANIFEST,
            dry_run=ctx.dry_run,
        )

    def _install_skills(self, ctx: InstallContext) -> list[ChangeResult]:
        if ctx.host_isolated_skills:
            return [
                copy_tree(
                    ctx.plugin_root / CURSOR_SKILLS_DIR,
                    ctx.target / CURSOR_SKILLS_DIR,
                    manifest_name=CURSOR_HOST_SKILLS_MANIFEST,
                    dry_run=ctx.dry_run,
                )
            ]
        return ctx.run_state.ensure_shared_skills(ctx)


def _hook_command(ctx: InstallContext, mode: str) -> str:
    # Cursor's hooks.json takes a single shell-executable string per hook
    # entry. POSIX shell and Windows cmd.exe have different quoting rules,
    # so we pick the right stdlib helper at install time. See also
    # cursor/cursor#3386 for a related Cursor-side path-quoting bug on
    # Windows; worth checking if hook commands misbehave there.
    hook_script = runtime_root() / CURSOR_HOOK_SCRIPT_RELPATH
    state_dir = ctx.target / CURSOR_STATE_DIR
    parts = [
        PYTHON_COMMAND,
        str(hook_script),
        "--mode",
        mode,
        "--state-dir",
        str(state_dir),
    ]
    if platform.system() == "Windows":
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)
