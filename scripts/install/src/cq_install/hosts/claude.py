"""Claude Code host adapter (thin marketplace wrapper)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from cq_install.context import Action, ChangeResult, InstallContext
from cq_install.hosts.base import HostDef

# Claude CLI marketplace semantics:
# - `claude plugin marketplace add` takes the GitHub source slug.
# - `claude plugin install` and `claude plugin marketplace remove` both take
#   the derived marketplace identifier (the repo short name).
# The cq marketplace currently exposes a single plugin with that same
# identifier, so one constant is sufficient for both commands.
CLAUDE_CLI = "claude"
CLAUDE_MARKETPLACE_ID = "cq"
CLAUDE_MARKETPLACE_SOURCE_SLUG = "mozilla-ai/cq"


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
        if not ctx.dry_run:
            self._require_cli()
        commands = [
            [CLAUDE_CLI, "plugin", "marketplace", "add", CLAUDE_MARKETPLACE_SOURCE_SLUG],
            [CLAUDE_CLI, "plugin", "install", CLAUDE_MARKETPLACE_ID],
        ]
        return [self._run_each(commands, ctx, action=Action.CREATED)]

    def uninstall(self, ctx: InstallContext) -> list[ChangeResult]:
        """Run `claude plugin marketplace remove`.

        Removing the marketplace unregisters the plugin as well, so no
        separate `claude plugin uninstall` call is needed.
        """
        if not ctx.dry_run:
            self._require_cli()
        commands = [
            [CLAUDE_CLI, "plugin", "marketplace", "remove", CLAUDE_MARKETPLACE_ID],
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
            result = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if result.returncode != 0:
                details = [
                    f"command failed: {' '.join(cmd)}",
                    f"return code: {result.returncode}",
                ]
                stderr = (result.stderr or "").strip()
                if stderr:
                    details.append(f"stderr: {stderr}")
                stdout = (result.stdout or "").strip()
                if stdout:
                    details.append(f"stdout: {stdout}")
                raise RuntimeError("\n".join(details))
        return ChangeResult(action=action, path=Path("claude marketplace"))
