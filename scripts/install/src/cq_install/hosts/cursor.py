"""Cursor host adapter."""

from __future__ import annotations

from pathlib import Path

from cq_install.context import ChangeResult, InstallContext
from cq_install.hosts.base import HostDef


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
        raise NotImplementedError

    def uninstall(self, ctx: InstallContext) -> list[ChangeResult]:
        """Remove cq from the Cursor target."""
        raise NotImplementedError
