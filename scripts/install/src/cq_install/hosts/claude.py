"""Claude Code host adapter (thin marketplace wrapper)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from cq_install.context import Action, ChangeResult, InstallContext
from cq_install.hosts.base import HostDef

# Claude CLI bin name, GitHub source slug, marketplace short name, and plugin name.
# `claude plugin marketplace add` takes the source slug (owner/repo); `remove`
# takes the derived short name (just the repo portion). The plugin itself is
# referenced by the same short name as the marketplace, since the cq marketplace
# exposes a single plugin of the same name. Removing the marketplace
# automatically unregisters any plugins installed from it, so uninstall only
# needs the one call.
CLAUDE_CLI = "claude"
CLAUDE_MARKETPLACE_NAME = "cq"
CLAUDE_MARKETPLACE_SOURCE = "mozilla-ai/cq"
CLAUDE_PLUGIN_NAME = "cq"


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
            [CLAUDE_CLI, "plugin", "marketplace", "add", CLAUDE_MARKETPLACE_SOURCE],
            [CLAUDE_CLI, "plugin", "install", CLAUDE_PLUGIN_NAME],
        ]
        return [self._run_each(commands, ctx, action=Action.CREATED)]

    def uninstall(self, ctx: InstallContext) -> list[ChangeResult]:
        """Run `claude plugin marketplace remove`.

        Removing the marketplace unregisters the plugin as well, so no
        separate `claude plugin uninstall` call is needed.
        """
        self._require_cli()
        commands = [
            [CLAUDE_CLI, "plugin", "marketplace", "remove", CLAUDE_MARKETPLACE_NAME],
        ]
        return [self._run_each(commands, ctx, action=Action.REMOVED)]

    def _require_cli(self) -> None:
        if shutil.which(CLAUDE_CLI) is None:
            raise RuntimeError(f"{CLAUDE_CLI} CLI not found on PATH; install Claude Code first.")

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
