"""Windsurf host adapter."""

from __future__ import annotations

from pathlib import Path

from cq_install.common import (
    copy_tree,
    remove_copied_tree,
    remove_json_entry,
    upsert_json_entry,
)
from cq_install.content import CQ_MCP_KEY, cq_binary_name
from cq_install.context import ChangeResult, InstallContext
from cq_install.hosts.base import HostDef
from cq_install.runtime import runtime_root

WINDSURF_HOST_SKILLS_MANIFEST = ".cq-install-manifest.json"
WINDSURF_MCP_FILE = "mcp_config.json"
WINDSURF_MCP_SERVERS_KEY = "mcpServers"
WINDSURF_SKILLS_DIR = "skills"

# Windsurf stores its config under ~/.codeium/windsurf/ on every platform.
# Confirmed against a live Windows 11 install.
WINDSURF_GLOBAL_TARGET = Path(".codeium") / "windsurf"


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
        return Path.home() / WINDSURF_GLOBAL_TARGET

    def install(self, ctx: InstallContext) -> list[ChangeResult]:
        """Install cq into the Windsurf target."""
        results: list[ChangeResult] = []
        if ctx.host_isolated_skills:
            results.append(
                copy_tree(
                    ctx.plugin_root / WINDSURF_SKILLS_DIR,
                    ctx.target / WINDSURF_SKILLS_DIR,
                    manifest_name=WINDSURF_HOST_SKILLS_MANIFEST,
                    dry_run=ctx.dry_run,
                )
            )
        else:
            results.extend(ctx.run_state.ensure_shared_skills(ctx))
        results.extend(ctx.run_state.ensure_cq_binary(ctx))
        binary_path = runtime_root() / "bin" / cq_binary_name()
        results.append(
            upsert_json_entry(
                ctx.target / WINDSURF_MCP_FILE,
                [WINDSURF_MCP_SERVERS_KEY, CQ_MCP_KEY],
                {
                    "command": str(binary_path),
                    "args": ["mcp"],
                },
                dry_run=ctx.dry_run,
            )
        )
        return results

    def uninstall(self, ctx: InstallContext) -> list[ChangeResult]:
        """Remove cq from the Windsurf target."""
        results: list[ChangeResult] = [
            remove_copied_tree(
                ctx.target / WINDSURF_SKILLS_DIR,
                manifest_name=WINDSURF_HOST_SKILLS_MANIFEST,
                dry_run=ctx.dry_run,
            ),
            remove_json_entry(
                ctx.target / WINDSURF_MCP_FILE,
                [WINDSURF_MCP_SERVERS_KEY, CQ_MCP_KEY],
                dry_run=ctx.dry_run,
            ),
        ]
        return results
