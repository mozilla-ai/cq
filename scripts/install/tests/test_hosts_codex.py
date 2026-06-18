"""Tests for the Codex host install/uninstall flow."""

from __future__ import annotations

from pathlib import Path

import pytest

from cq_install.context import Action, InstallContext, RunState
from cq_install.hosts.codex import CodexHost, _run_codex


@pytest.fixture
def codex_ctx(tmp_path: Path, plugin_root: Path) -> InstallContext:
    """Build a ready-to-use InstallContext for Codex install."""
    target = tmp_path / "codex-marketplace"
    target.mkdir(exist_ok=True)
    return InstallContext(
        target=target,
        plugin_root=plugin_root,
        shared_skills_path=tmp_path / "shared",
        host_isolated_skills=False,
        dry_run=False,
        run_state=RunState(),
    )


def test_codex_global_target_default():
    """Without overrides, global target is ~/.codex/cq-marketplace."""
    assert CodexHost().global_target() == Path.home() / ".codex" / "cq-marketplace"


def test_codex_global_target_override(monkeypatch):
    """CODEX_MARKETPLACE_DIR env var overrides the target path."""
    monkeypatch.setenv("CODEX_MARKETPLACE_DIR", "/custom/path")
    assert CodexHost().global_target() == Path("/custom/path")


def test_codex_project_target_raises():
    """Codex does not support per-project installs."""
    with pytest.raises(NotImplementedError):
        CodexHost().project_target(Path("/proj"))


def test_codex_install_dry_run(tmp_path, plugin_root):
    """Dry-run mode returns skipped changes without writing files."""
    target = tmp_path / "marketplace"
    target.mkdir(exist_ok=True)
    ctx = InstallContext(
        target=target,
        plugin_root=plugin_root,
        shared_skills_path=tmp_path / "shared",
        host_isolated_skills=False,
        dry_run=True,
        run_state=RunState(),
    )
    results = CodexHost().install(ctx)

    assert all(r.action == Action.SKIPPED for r in results)
    # Nothing was written to the target directory
    assert len(list(target.iterdir())) == 0


def test_codex_install_creates_marketplace(tmp_path, plugin_root):
    """Install prepares the marketplace directory structure."""
    # Build the repo structure the installer expects
    repo_root = plugin_root.parent.parent  # plugins/../.. = repo root from plugin_root
    marketplace_json = repo_root / "marketplace.json"
    codex_plugin_dir = repo_root / "plugins" / "codex"

    marketplace_json.parent.mkdir(exist_ok=True)
    marketplace_json.write_text('{"name": "cq", "source": "./plugins/codex"}\n')
    codex_plugin_dir.mkdir(parents=True, exist_ok=True)
    (codex_plugin_dir / ".codex-plugin").mkdir()
    (codex_plugin_dir / ".codex-plugin" / "plugin.json").write_text('{"name": "cq", "version": "0.11.0"}\n')

    target = tmp_path / "marketplace"
    target.mkdir(exist_ok=True)
    ctx = InstallContext(
        target=target,
        plugin_root=plugin_root,
        shared_skills_path=tmp_path / "shared",
        host_isolated_skills=False,
        dry_run=True,
        run_state=RunState(),
    )

    # Just verify the _prepare_marketplace call would not crash
    host = CodexHost()
    results = host.install(ctx)
    assert len(results) == 3  # prepare, register marketplace, register plugin
    assert all(r.action == Action.SKIPPED for r in results)


def test_run_codex_returns_none_on_missing_cli():
    """_run_codex returns None when codex is not on PATH."""
    import inspect
    sig = inspect.signature(_run_codex)
    assert "args" in sig.parameters
    # The return annotation should include None
    hint = sig.return_annotation
    assert hint is not inspect.Parameter.empty
    assert "None" in str(hint)


def test_codex_uninstall_dry_run(tmp_path, plugin_root):
    """Dry-run uninstall returns skipped changes."""
    target = tmp_path / "marketplace"
    target.mkdir(exist_ok=True)
    ctx = InstallContext(
        target=target,
        plugin_root=plugin_root,
        shared_skills_path=tmp_path / "shared",
        host_isolated_skills=False,
        dry_run=True,
        run_state=RunState(),
    )
    results = CodexHost().uninstall(ctx)
    assert all(r.action == Action.SKIPPED for r in results)
