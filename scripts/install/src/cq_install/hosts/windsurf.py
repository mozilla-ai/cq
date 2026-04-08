"""Windsurf host adapter."""

from __future__ import annotations

from pathlib import Path

from cq_install.context import ChangeResult, InstallContext
from cq_install.hosts.base import HostDef


class WindsurfHost(HostDef):
    """Adapter for the Windsurf editor host.

    Windsurf stores its config under `~/.codeium/windsurf/` on every
    platform. Confirmed against a live Windows 11 install where the
    directory contains Cascade/brain/memories subdirs. `Path.home()`
    resolves to `%USERPROFILE%` on Windows, so this works without any
    platform branching.
    """

    name = "windsurf"
    supports_project = False

    def global_target(self) -> Path:
        """Return the global Windsurf config dir."""
        return Path.home() / ".codeium" / "windsurf"

    def install(self, ctx: InstallContext) -> list[ChangeResult]:
        """Install cq into the Windsurf target."""
        raise NotImplementedError

    def uninstall(self, ctx: InstallContext) -> list[ChangeResult]:
        """Remove cq from the Windsurf target."""
        raise NotImplementedError
