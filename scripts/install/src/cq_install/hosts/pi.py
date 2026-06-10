"""Pi (pi.dev) host adapter.

Pi has no native MCP, so cq integrates via its standalone CLI: the cq block
written into Pi's AGENTS.md maps each cq action to a `cq <verb> --format json`
invocation the agent runs through its shell. The skill and commands are
installed unchanged (commands only have their `name:` frontmatter stripped).
"""

from __future__ import annotations

from pathlib import Path

from cq_install.common import (
    copy_tree,
    remove_copied_tree,
    remove_markdown_block,
    upsert_markdown_block,
)
from cq_install.content import (
    CQ_BLOCK_END,
    CQ_BLOCK_START,
    cq_binary_name,
)
from cq_install.context import Action, ChangeResult, InstallContext
from cq_install.hosts.base import HostDef
from cq_install.pi_commands import transform_command
from cq_install.runtime import runtime_root

PI_AGENTS_FILE = "AGENTS.md"
PI_COMMANDS_DIR = "commands"
PI_HOST_SKILLS_MANIFEST = ".cq-install-manifest.json"
PI_PROMPTS_DIR = "prompts"
PI_SKILLS_DIR = "skills"

# Pi reads global config from ~/.pi/agent/ and per-project config from
# <project>/.pi/ (note the asymmetry: global has an extra `agent` segment).
PI_GLOBAL_TARGET = Path(".pi") / "agent"
PI_PROJECT_TARGET = ".pi"


class PiHost(HostDef):
    """Adapter for the Pi coding agent."""

    name = "pi"

    def global_target(self) -> Path:
        """Return the global Pi config dir (~/.pi/agent)."""
        return Path.home() / PI_GLOBAL_TARGET

    def install(self, ctx: InstallContext) -> list[ChangeResult]:
        """Install cq into the Pi target."""
        results: list[ChangeResult] = []
        results.extend(self._install_skills(ctx))
        results.extend(ctx.run_state.ensure_cq_binary(ctx))
        results.extend(self._install_prompts(ctx))
        results.append(self._install_agents_md(ctx))
        return results

    def project_target(self, project: Path) -> Path:
        """Return the per-project Pi config dir (<project>/.pi)."""
        return project / PI_PROJECT_TARGET

    def uninstall(self, ctx: InstallContext) -> list[ChangeResult]:
        """Remove cq from the Pi target."""
        return [
            remove_copied_tree(
                ctx.target / PI_SKILLS_DIR,
                manifest_name=PI_HOST_SKILLS_MANIFEST,
                dry_run=ctx.dry_run,
            ),
            self._uninstall_prompts(ctx),
            remove_markdown_block(
                ctx.target / PI_AGENTS_FILE,
                CQ_BLOCK_START,
                CQ_BLOCK_END,
                dry_run=ctx.dry_run,
            ),
        ]

    def _install_agents_md(self, ctx: InstallContext) -> ChangeResult:
        binary_path = runtime_root() / "bin" / cq_binary_name()
        return upsert_markdown_block(
            ctx.target / PI_AGENTS_FILE,
            CQ_BLOCK_START,
            CQ_BLOCK_END,
            _agents_block(binary_path),
            dry_run=ctx.dry_run,
        )

    def _install_prompts(self, ctx: InstallContext) -> list[ChangeResult]:
        results: list[ChangeResult] = []
        commands_src = ctx.plugin_root / PI_COMMANDS_DIR
        prompts_dst = ctx.target / PI_PROMPTS_DIR
        for cmd_file in sorted(commands_src.glob("*.md")):
            transformed = transform_command(cmd_file.read_text())
            target_file = prompts_dst / f"cq-{cmd_file.name}"
            results.append(_write_text_idempotent(target_file, transformed, dry_run=ctx.dry_run))
        return results

    def _install_skills(self, ctx: InstallContext) -> list[ChangeResult]:
        if ctx.host_isolated_skills:
            return [
                copy_tree(
                    ctx.plugin_root / PI_SKILLS_DIR,
                    ctx.target / PI_SKILLS_DIR,
                    manifest_name=PI_HOST_SKILLS_MANIFEST,
                    dry_run=ctx.dry_run,
                )
            ]
        return ctx.run_state.ensure_shared_skills(ctx)

    def _uninstall_prompts(self, ctx: InstallContext) -> ChangeResult:
        commands_src = ctx.plugin_root / PI_COMMANDS_DIR
        prompts_dst = ctx.target / PI_PROMPTS_DIR
        removed = False
        skipped = False
        for cmd_file in sorted(commands_src.glob("*.md")):
            target_file = prompts_dst / f"cq-{cmd_file.name}"
            if not target_file.exists():
                continue
            expected = transform_command(cmd_file.read_text())
            if target_file.read_text() != expected:
                skipped = True
                continue
            if not ctx.dry_run:
                target_file.unlink()
            removed = True
        if removed and prompts_dst.exists() and not any(prompts_dst.iterdir()) and not ctx.dry_run:
            prompts_dst.rmdir()
        if skipped:
            return ChangeResult(
                action=Action.SKIPPED,
                path=prompts_dst,
                detail="user-modified prompt files left in place",
            )
        return ChangeResult(
            action=Action.REMOVED if removed else Action.UNCHANGED,
            path=prompts_dst,
        )


def _agents_block(binary_path: Path) -> str:
    cq = str(binary_path)
    # Each mapping line is assembled from fragments so the source stays within
    # the line-length limit; the rendered markdown line is intentionally long.
    query = (
        f"- query   -> `{cq} query --domain <d> [--domain <d> ...] "
        "[--language <l>] [--framework <f>] [--pattern <p>] [--limit <n>] --format json`"
    )
    propose = (
        f"- propose -> `{cq} propose --summary <s> --detail <d> --action <a> --domain <d> "
        "[--domain <d> ...] [--language <l>] [--framework <f>] [--pattern <p>] --format json`"
    )
    confirm = f"- confirm -> `{cq} confirm <unit_id>`"
    flag = (
        f"- flag    -> `{cq} flag <unit_id> --reason <stale|incorrect|duplicate> "
        "[--detail <text>] [--duplicate-of <id>]`"
    )
    status = f"- status  -> `{cq} status --format json`"
    mapping = "\n".join([query, propose, confirm, flag, status])
    return f"""{CQ_BLOCK_START}
## CQ

Before starting any implementation task, load the `cq` skill and follow its Core Protocol.

This runtime has no cq MCP server. The cq skill and `/cq-*` commands describe the protocol using
MCP-tool wording; in this runtime, perform every cq action by running the cq CLI through your shell.
Parse `--format json` output for the commands that support it (query, propose, status); confirm and
flag return plain text. The cq binary is: `{cq}`. Map each action:

{mapping}

Repeat `--domain` once per tag.
{CQ_BLOCK_END}"""


def _write_text_idempotent(path: Path, content: str, *, dry_run: bool) -> ChangeResult:
    if path.exists() and path.read_text() == content:
        return ChangeResult(action=Action.UNCHANGED, path=path)
    action = Action.UPDATED if path.exists() else Action.CREATED
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return ChangeResult(action=action, path=path)
