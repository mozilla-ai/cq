"""HostDef base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from cq_install.context import ChangeResult, InstallContext


class HostDef(ABC):
    """Base class for host adapters."""

    name: str
    supports_project: bool = True
    supports_host_isolated: bool = True

    @abstractmethod
    def global_target(self) -> Path:
        """Return the user's global config dir for this host."""

    def project_target(self, project: Path) -> Path:
        """Return the per-project config dir for this host."""
        raise NotImplementedError

    @abstractmethod
    def install(self, ctx: InstallContext) -> list[ChangeResult]:
        """Install cq into the target. Return per-step results."""

    @abstractmethod
    def uninstall(self, ctx: InstallContext) -> list[ChangeResult]:
        """Remove cq from the target. Return per-step results."""
