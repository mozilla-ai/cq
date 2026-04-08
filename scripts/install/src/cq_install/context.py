"""Shared types: ChangeResult, Action, InstallContext, RunState."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Action(Enum):
    """The kind of change a primitive applied (or would apply in dry-run mode)."""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    REMOVED = "removed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ChangeResult:
    """The outcome of a single primitive call."""

    action: Action
    path: Path
    detail: str = ""


@dataclass
class RunState:
    """In-memory dedup tracker for a single installer invocation."""

    _done: set[tuple[str, str]] = field(default_factory=set)

    def ensure_shared_skills(self, ctx: InstallContext) -> list[ChangeResult]:
        """Run the shared-skill install for ctx exactly once per target path."""
        from cq_install.common import copy_tree

        if not self.mark_done("shared-skills", ctx.shared_skills_path):
            return []
        result = copy_tree(
            ctx.plugin_root / "skills",
            ctx.shared_skills_path,
            manifest_name=".cq-install-manifest.json",
            dry_run=ctx.dry_run,
        )
        return [result]

    def mark_done(self, step: str, target: Path) -> bool:
        """Record that `step` ran for `target`. Returns True if this is the first time."""
        key = (step, str(target))
        if key in self._done:
            return False
        self._done.add(key)
        return True


@dataclass(frozen=True)
class InstallContext:
    """Per-host install context resolved from CLI arguments."""

    target: Path
    plugin_root: Path
    bootstrap_path: Path
    shared_skills_path: Path
    host_isolated_skills: bool
    dry_run: bool
    run_state: RunState
