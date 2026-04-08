"""OpenCode host adapter."""

from __future__ import annotations

import json
from pathlib import Path

from cq_install.common import (
    copy_tree,
    remove_copied_tree,
    remove_json_entry,
    remove_markdown_block,
    upsert_json_entry,
    upsert_markdown_block,
)
from cq_install.content import (
    CQ_AGENTS_BLOCK,
    CQ_BLOCK_END,
    CQ_BLOCK_START,
    PYTHON_COMMAND,
)
from cq_install.context import Action, ChangeResult, InstallContext
from cq_install.hosts.base import HostDef
from cq_install.opencode_commands import transform_command

OPENCODE_HOST_SKILLS_MANIFEST = ".cq-install-manifest.json"
OPENCODE_SCHEMA_URL = "https://opencode.ai/config.json"


class OpenCodeHost(HostDef):
    """Adapter for the OpenCode host."""

    name = "opencode"

    def global_target(self) -> Path:
        """Return the global OpenCode config dir."""
        return Path.home() / ".config" / "opencode"

    def project_target(self, project: Path) -> Path:
        """Return the per-project OpenCode config dir."""
        return project / ".opencode"

    def install(self, ctx: InstallContext) -> list[ChangeResult]:
        """Install cq into the OpenCode target."""
        results: list[ChangeResult] = []
        results.extend(self._install_skills(ctx))
        results.extend(self._install_commands(ctx))
        results.append(self._install_mcp(ctx))
        results.append(self._install_agents_md(ctx))
        return results

    def uninstall(self, ctx: InstallContext) -> list[ChangeResult]:
        """Remove cq from the OpenCode target."""
        results: list[ChangeResult] = []
        results.append(
            remove_copied_tree(
                ctx.target / "skills",
                manifest_name=OPENCODE_HOST_SKILLS_MANIFEST,
                dry_run=ctx.dry_run,
            )
        )
        results.append(self._uninstall_commands(ctx))
        results.append(
            remove_json_entry(
                ctx.target / "opencode.json",
                ["mcp", "cq"],
                dry_run=ctx.dry_run,
            )
        )
        results.append(
            remove_markdown_block(
                ctx.target / "AGENTS.md",
                CQ_BLOCK_START,
                CQ_BLOCK_END,
                dry_run=ctx.dry_run,
            )
        )
        return results

    def _install_agents_md(self, ctx: InstallContext) -> ChangeResult:
        return upsert_markdown_block(
            ctx.target / "AGENTS.md",
            CQ_BLOCK_START,
            CQ_BLOCK_END,
            CQ_AGENTS_BLOCK,
            dry_run=ctx.dry_run,
        )

    def _install_commands(self, ctx: InstallContext) -> list[ChangeResult]:
        results: list[ChangeResult] = []
        commands_src = ctx.plugin_root / "commands"
        commands_dst = ctx.target / "commands"
        for cmd_file in sorted(commands_src.glob("*.md")):
            transformed = transform_command(cmd_file.read_text())
            target_file = commands_dst / cmd_file.name
            results.append(_write_text_idempotent(target_file, transformed, dry_run=ctx.dry_run))
        return results

    def _install_mcp(self, ctx: InstallContext) -> ChangeResult:
        config_path = ctx.target / "opencode.json"
        # Seed $schema on fresh-file creation only. The URL gives OpenCode
        # autocomplete and validation for the config shape; writing it when
        # we're creating the file from scratch is a user-experience nicety.
        # We never rewrite it on existing files so user overrides (e.g. a
        # local schema cache URL) survive subsequent re-installs.
        if not config_path.exists() and not ctx.dry_run:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps({"$schema": OPENCODE_SCHEMA_URL}, indent=2) + "\n")
        return upsert_json_entry(
            config_path,
            ["mcp", "cq"],
            {
                "type": "local",
                # Written as a literal name (not an absolute path) so it
                # PATH-resolves at OpenCode's invocation time; see the
                # PYTHON_COMMAND comment in cq_install.content for the
                # Windows rationale.
                "command": [PYTHON_COMMAND, str(ctx.bootstrap_path)],
            },
            dry_run=ctx.dry_run,
        )

    def _install_skills(self, ctx: InstallContext) -> list[ChangeResult]:
        if ctx.host_isolated_skills:
            return [
                copy_tree(
                    ctx.plugin_root / "skills",
                    ctx.target / "skills",
                    manifest_name=OPENCODE_HOST_SKILLS_MANIFEST,
                    dry_run=ctx.dry_run,
                )
            ]
        return ctx.run_state.ensure_shared_skills(ctx)

    def _uninstall_commands(self, ctx: InstallContext) -> ChangeResult:
        commands_src = ctx.plugin_root / "commands"
        commands_dst = ctx.target / "commands"
        removed = False
        for cmd_file in commands_src.glob("*.md"):
            target_file = commands_dst / cmd_file.name
            if target_file.exists():
                if not ctx.dry_run:
                    target_file.unlink()
                removed = True
        if removed and commands_dst.exists() and not any(commands_dst.iterdir()) and not ctx.dry_run:
            commands_dst.rmdir()
        return ChangeResult(
            action=Action.REMOVED if removed else Action.UNCHANGED,
            path=commands_dst,
        )


def _write_text_idempotent(path: Path, content: str, *, dry_run: bool) -> ChangeResult:
    if path.exists() and path.read_text() == content:
        return ChangeResult(action=Action.UNCHANGED, path=path)
    action = Action.UPDATED if path.exists() else Action.CREATED
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return ChangeResult(action=action, path=path)
