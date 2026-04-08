"""Cursor host adapter."""

from __future__ import annotations

import hashlib
import platform
import shlex
import subprocess
from pathlib import Path

from cq_install.common import (
    copy_tree,
    remove_copied_tree,
    remove_hook_entry,
    remove_json_entry,
    remove_owned_file,
    upsert_hook_entry,
    upsert_json_entry,
    write_if_missing,
)
from cq_install.content import PYTHON_COMMAND
from cq_install.context import ChangeResult, InstallContext
from cq_install.hosts.base import HostDef

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

CURSOR_HOST_SKILLS_MANIFEST = ".cq-install-manifest.json"
CURSOR_RULE_HASH = hashlib.sha256(CURSOR_RULE_CONTENT.encode()).hexdigest()


class CursorHost(HostDef):
    """Adapter for the Cursor editor host."""

    name = "cursor"

    def global_target(self) -> Path:
        """Return the global Cursor config dir."""
        return Path.home() / ".cursor"

    def project_target(self, project: Path) -> Path:
        """Return the per-project Cursor config dir."""
        return project / ".cursor"

    def install(self, ctx: InstallContext) -> list[ChangeResult]:
        """Install cq into the Cursor target."""
        results: list[ChangeResult] = []
        results.extend(self._install_skills(ctx))
        results.append(self._install_mcp(ctx))
        results.append(
            write_if_missing(
                ctx.target / "rules" / "cq.mdc",
                CURSOR_RULE_CONTENT,
                dry_run=ctx.dry_run,
            )
        )
        results.extend(self._install_hooks(ctx))
        return results

    def uninstall(self, ctx: InstallContext) -> list[ChangeResult]:
        """Remove cq from the Cursor target."""
        results: list[ChangeResult] = []
        results.append(
            remove_copied_tree(
                ctx.target / "skills",
                manifest_name=CURSOR_HOST_SKILLS_MANIFEST,
                dry_run=ctx.dry_run,
            )
        )
        results.append(
            remove_json_entry(
                ctx.target / "mcp.json",
                ["mcpServers", "cq"],
                dry_run=ctx.dry_run,
            )
        )
        results.append(
            remove_owned_file(
                ctx.target / "rules" / "cq.mdc",
                expected_content_hash=CURSOR_RULE_HASH,
                dry_run=ctx.dry_run,
            )
        )
        for hook_name, mode in CURSOR_HOOK_MODES:
            results.append(
                remove_hook_entry(
                    ctx.target / "hooks.json",
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
                    ctx.target / "hooks.json",
                    hook_name=hook_name,
                    command=_hook_command(ctx, mode),
                    legacy_commands=CURSOR_LEGACY_HOOK_COMMANDS,
                    dry_run=ctx.dry_run,
                )
            )
        return results

    def _install_mcp(self, ctx: InstallContext) -> ChangeResult:
        return upsert_json_entry(
            ctx.target / "mcp.json",
            ["mcpServers", "cq"],
            {
                # Literal command name so PATH resolves at Cursor's invocation
                # time; see PYTHON_COMMAND rationale in cq_install.content.
                "command": PYTHON_COMMAND,
                "args": [str(ctx.bootstrap_path)],
            },
            dry_run=ctx.dry_run,
        )

    def _install_skills(self, ctx: InstallContext) -> list[ChangeResult]:
        if ctx.host_isolated_skills:
            return [
                copy_tree(
                    ctx.plugin_root / "skills",
                    ctx.target / "skills",
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
    hook_script = ctx.plugin_root / "hooks" / "cursor" / "cq_cursor_hook.py"
    state_dir = ctx.target / "cq-hook-state"
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
