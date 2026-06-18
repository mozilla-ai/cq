"""Codex host adapter."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from cq_install.context import Action, ChangeResult, InstallContext
from cq_install.hosts.base import HostDef

CODEX_MARKETPLACE_DIR = Path(".codex") / "cq-marketplace"


PLUGIN_SOURCE_RELPATH = Path("plugins") / "codex"


class CodexHost(HostDef):
    """Adapter for OpenAI Codex CLI."""

    name = "codex"
    supports_project = False
    supports_host_isolated = False

    def global_target(self) -> Path:
        """Return the marketplace directory for Codex plugin registration."""
        override = _marketplace_override()
        if override:
            return override
        return Path.home() / CODEX_MARKETPLACE_DIR

    def install(self, ctx: InstallContext) -> list[ChangeResult]:
        """Install cq into Codex via its plugin marketplace."""
        results: list[ChangeResult] = []

        results.append(self._prepare_marketplace(ctx))
        results.extend(ctx.run_state.ensure_cq_binary(ctx))
        results.extend(self._register_with_codex(ctx))

        return results

    def uninstall(self, ctx: InstallContext) -> list[ChangeResult]:
        """Remove cq from Codex."""
        results: list[ChangeResult] = []

        results.extend(self._unregister_from_codex(ctx))
        results.append(self._remove_marketplace(ctx))

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prepare_marketplace(self, ctx: InstallContext) -> ChangeResult:
        """Clone relevant files into the marketplace directory.

        Copies ``marketplace.json`` and ``plugins/codex/`` into
        ``ctx.target`` so that Codex can discover the plugin via its
        local marketplace.
        """
        if ctx.dry_run:
            return ChangeResult(
                action=Action.SKIPPED,
                path=ctx.target,
                detail="would prepare Codex marketplace directory",
            )

        repo_root = ctx.plugin_root.parent.parent
        marketplace_src = repo_root / "marketplace.json"
        plugin_src = repo_root / PLUGIN_SOURCE_RELPATH

        # Wipe and recreate — Codex's local-marketplace add fails when the
        # destination already exists (a known CLI bug).
        if ctx.target.exists():
            shutil.rmtree(ctx.target)
        ctx.target.mkdir(parents=True, exist_ok=True)

        # Copy marketplace.json
        if marketplace_src.exists():
            # Codex expects manifest at .agents/plugins/marketplace.json
            manifest_dst = ctx.target / ".agents" / "plugins"
            manifest_dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(marketplace_src, manifest_dst / "marketplace.json")

        # Copy plugin files (resolves symlinks — notably scripts/ -> ../cq/scripts)
        plugin_dst = ctx.target / PLUGIN_SOURCE_RELPATH
        plugin_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(plugin_src, plugin_dst, symlinks=False)

        return ChangeResult(
            action=Action.CREATED,
            path=ctx.target,
            detail="Codex marketplace directory prepared",
        )

    def _remove_marketplace(self, ctx: InstallContext) -> ChangeResult:
        if ctx.dry_run:
            return ChangeResult(
                action=Action.SKIPPED,
                path=ctx.target,
                detail="would remove Codex marketplace directory",
            )
        if not ctx.target.exists():
            return ChangeResult(action=Action.UNCHANGED, path=ctx.target)
        shutil.rmtree(ctx.target)
        return ChangeResult(action=Action.REMOVED, path=ctx.target)

    def _register_with_codex(self, ctx: InstallContext) -> list[ChangeResult]:
        """Run ``codex plugin marketplace add`` + ``codex plugin add``."""
        results: list[ChangeResult] = []

        if ctx.dry_run:
            results.append(
                ChangeResult(
                    action=Action.SKIPPED,
                    path=ctx.target,
                    detail="would register marketplace and plugin with Codex CLI",
                )
            )
            results.append(
                ChangeResult(
                    action=Action.SKIPPED,
                    path=ctx.target / PLUGIN_SOURCE_RELPATH,
                    detail="would add cq plugin",
                )
            )
            return results

        # 1. marketplace add — skip if already registered
        rc = _run_codex(["plugin", "marketplace", "list"])
        if rc is None:
            results.append(
                ChangeResult(
                    action=Action.SKIPPED,
                    path=ctx.target,
                    detail="codex CLI not found — add the marketplace manually: codex plugin marketplace add <dir>",
                )
            )
            return results
        already = str(ctx.target) in rc.stdout if rc.returncode == 0 else False

        if already:
            results.append(
                ChangeResult(
                    action=Action.UNCHANGED,
                    path=ctx.target,
                    detail="marketplace already registered",
                )
            )
        else:
            rc = _run_codex(["plugin", "marketplace", "add", str(ctx.target)])
            if rc.returncode != 0:
                results.append(
                    ChangeResult(
                        action=Action.SKIPPED,
                        path=ctx.target,
                        detail=f"codex plugin marketplace add failed: {rc.stderr.strip()}",
                    )
                )
                return results
            results.append(
                ChangeResult(
                    action=Action.CREATED,
                    path=ctx.target,
                    detail="marketplace registered",
                )
            )

        # 2. plugin add — skip if already installed
        rc = _run_codex(["plugin", "list"])
        if rc is None:
            results.append(
                ChangeResult(
                    action=Action.SKIPPED,
                    path=ctx.target / PLUGIN_SOURCE_RELPATH,
                    detail="codex CLI not found — add the plugin manually: codex plugin add cq@cq",
                )
            )
            return results
        if rc.returncode == 0 and re.search(r"cq@cq\s+installed", rc.stdout):
            results.append(
                ChangeResult(
                    action=Action.UNCHANGED,
                    path=ctx.target / PLUGIN_SOURCE_RELPATH,
                    detail="plugin already installed",
                )
            )
            return results

        rc = _run_codex(["plugin", "add", "cq@cq"])
        if rc.returncode != 0:
            results.append(
                ChangeResult(
                    action=Action.SKIPPED,
                    path=ctx.target / PLUGIN_SOURCE_RELPATH,
                    detail=f"codex plugin add failed: {rc.stderr.strip()}",
                )
            )
            return results

        results.append(
            ChangeResult(
                action=Action.CREATED,
                path=ctx.target / PLUGIN_SOURCE_RELPATH,
                detail="cq plugin installed in Codex",
            )
        )
        return results

    def _unregister_from_codex(self, ctx: InstallContext) -> list[ChangeResult]:
        results: list[ChangeResult] = []

        if ctx.dry_run:
            results.append(
                ChangeResult(
                    action=Action.SKIPPED,
                    path=ctx.target,
                    detail="would unregister plugin and marketplace from Codex CLI",
                )
            )
            return results

        rc_check = _run_codex(["version"])
        if rc_check is None:
            return results

        for cmd, label in [
            (["plugin", "remove", "cq"], "plugin removed"),
            (["plugin", "marketplace", "remove", "cq"], "marketplace removed"),
        ]:
            rc = _run_codex(cmd)
            if rc.returncode == 0:
                results.append(
                    ChangeResult(
                        action=Action.REMOVED,
                        path=ctx.target,
                        detail=label,
                    )
                )
            else:
                results.append(
                    ChangeResult(
                        action=Action.UNCHANGED,
                        path=ctx.target,
                        detail=f"{label} skipped ({rc.stderr.strip() or 'not installed'})",
                    )
                )
        return results


def _run_codex(args: list[str]) -> subprocess.CompletedProcess | None:
    """Run ``codex`` CLI with the given arguments.

    Returns ``None`` when the ``codex`` binary is not found on the system.
    """
    codex_bin = shutil.which("codex")
    if codex_bin is None:
        return None
    return subprocess.run(
        [codex_bin, *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def _marketplace_override() -> Path | None:
    """Check for CODEX_MARKETPLACE_DIR env override (for testing)."""
    import os

    val = os.environ.get("CODEX_MARKETPLACE_DIR")
    if val:
        return Path(val).resolve()
    return None
