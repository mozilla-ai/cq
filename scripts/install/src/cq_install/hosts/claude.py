"""Claude Code host adapter (thin marketplace wrapper)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from cq_install.context import Action, ChangeResult, InstallContext
from cq_install.hosts.base import HostDef


class ClaudeHost(HostDef):
    """Adapter for Claude Code via the plugin marketplace.

    Unlike the other hosts, Claude Code manages the plugin through its own
    `claude plugin marketplace` subcommand, so this adapter is a thin
    shell-out rather than a filesystem writer. `global_target` returns a
    sentinel path because it's never read.
    """

    name = "claude"
    supports_project = False
    supports_host_isolated = False

    def global_target(self) -> Path:
        """Return a sentinel path (unused; Claude manages its own config)."""
        return Path("/dev/null")

    def install(self, ctx: InstallContext) -> list[ChangeResult]:
        """Run `claude plugin marketplace add` and `claude plugin install`."""
        self._require_cli()
        commands = [
            ["claude", "plugin", "marketplace", "add", "mozilla-ai/cq"],
            ["claude", "plugin", "install", "cq"],
        ]
        return [self._run_each(commands, ctx, action=Action.CREATED)]

    def uninstall(self, ctx: InstallContext) -> list[ChangeResult]:
        """Run `claude plugin marketplace remove`."""
        self._require_cli()
        commands = [
            ["claude", "plugin", "marketplace", "remove", "mozilla-ai/cq"],
        ]
        return [self._run_each(commands, ctx, action=Action.REMOVED)]

    def _require_cli(self) -> None:
        if shutil.which("claude") is None:
            raise RuntimeError("claude CLI not found on PATH; install Claude Code first.")

    def _run_each(
        self,
        commands: list[list[str]],
        ctx: InstallContext,
        *,
        action: Action,
    ) -> ChangeResult:
        for cmd in commands:
            if ctx.dry_run:
                continue
            result = subprocess.run(cmd, check=False)
            if result.returncode != 0:
                raise RuntimeError(f"command failed: {' '.join(cmd)}")
        return ChangeResult(action=action, path=Path("claude marketplace"))
