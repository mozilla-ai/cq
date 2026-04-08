"""OpenCode host adapter."""

from __future__ import annotations

from pathlib import Path

from cq_install.context import ChangeResult, InstallContext
from cq_install.hosts.base import HostDef


class OpenCodeHost(HostDef):
    """Adapter for the OpenCode agent host."""

    name = "opencode"

    def global_target(self) -> Path:
        """Return the global OpenCode config dir."""
        return Path.home() / ".config" / "opencode"

    def project_target(self, project: Path) -> Path:
        """Return the per-project OpenCode config dir."""
        return project / ".opencode"

    def install(self, ctx: InstallContext) -> list[ChangeResult]:
        """Install cq into the OpenCode target."""
        raise NotImplementedError

    def uninstall(self, ctx: InstallContext) -> list[ChangeResult]:
        """Remove cq from the OpenCode target."""
        raise NotImplementedError
