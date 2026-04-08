"""Claude Code host adapter (thin marketplace wrapper)."""

from __future__ import annotations

from pathlib import Path

from cq_install.context import ChangeResult, InstallContext
from cq_install.hosts.base import HostDef


class ClaudeHost(HostDef):
    """Adapter for the Claude Code host.

    Claude Code installs cq via its native plugin marketplace, so this
    adapter does not write into any filesystem target the installer
    manages directly. `global_target()` returns a sentinel path that is
    never read; `supports_project` and `supports_host_isolated` are both
    False to reflect that neither project-level installs nor host-scoped
    skill isolation apply here.
    """

    name = "claude"
    supports_project = False
    supports_host_isolated = False

    def global_target(self) -> Path:
        """Return a sentinel path; Claude uses its own marketplace."""
        return Path("/dev/null")

    def install(self, ctx: InstallContext) -> list[ChangeResult]:
        """Install cq via the Claude Code marketplace."""
        raise NotImplementedError

    def uninstall(self, ctx: InstallContext) -> list[ChangeResult]:
        """Remove cq via the Claude Code marketplace."""
        raise NotImplementedError
