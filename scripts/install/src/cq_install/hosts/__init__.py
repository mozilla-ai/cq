"""Per-host install adapters."""

from __future__ import annotations

from cq_install.hosts.base import HostDef
from cq_install.hosts.claude import ClaudeHost
from cq_install.hosts.cursor import CursorHost
from cq_install.hosts.opencode import OpenCodeHost
from cq_install.hosts.windsurf import WindsurfHost

REGISTRY: dict[str, HostDef] = {
    "opencode": OpenCodeHost(),
    "cursor": CursorHost(),
    "windsurf": WindsurfHost(),
    "claude": ClaudeHost(),
}


def get_host(name: str) -> HostDef:
    """Look up a host by its target name."""
    if name not in REGISTRY:
        raise ValueError(f"unknown host: {name!s}; valid: {sorted(REGISTRY)}")
    return REGISTRY[name]
