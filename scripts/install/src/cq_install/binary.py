"""Installer-side binary fetch.

Dynamically loads ``plugins/cq/scripts/cq_binary.py`` from the plugin
source tree and delegates to its ``ensure_binary`` orchestrator. The
module-load dance exists because ``cq_install`` runs under its own
uv-managed venv while ``cq_binary`` lives in the plugin tree and must
stay stdlib-only so Claude can also run it.

Single source of truth: all fetch / version / cache logic is in
``cq_binary``; this module is purely the installer-side glue.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from cq_install.context import Action, ChangeResult

CQ_BINARY_RELPATH = Path("scripts") / "cq_binary.py"
BOOTSTRAP_METADATA_RELPATH = Path("scripts") / "bootstrap.json"


def ensure_cq_binary(plugin_root: Path, *, dry_run: bool = False) -> list[ChangeResult]:
    """Guarantee the cq binary is cached at the shared runtime path.

    Loads ``plugin_root/scripts/cq_binary.py`` via importlib and calls
    its ``ensure_binary`` with the required version from
    ``bootstrap.json``. Returns a single-element list of ``ChangeResult``
    so callers can extend their own result lists uniformly.
    """
    module = _load_cq_binary(plugin_root)

    metadata_path = plugin_root / BOOTSTRAP_METADATA_RELPATH
    required_version = module.load_required_version(metadata_path)
    if not required_version:
        raise RuntimeError(f"cq bootstrap metadata missing cli_version at {metadata_path}")

    bin_dir = module.shared_bin_dir()
    binary = bin_dir / module.cq_binary_name()

    already_valid = binary.is_file() and module.check_version(binary, required_version)
    detail_cached = f"cq v{required_version}"

    if dry_run:
        if already_valid:
            return [ChangeResult(action=Action.UNCHANGED, path=binary, detail=detail_cached)]
        return [
            ChangeResult(
                action=Action.SKIPPED,
                path=binary,
                detail=f"would fetch cq v{required_version}",
            )
        ]

    if already_valid:
        return [ChangeResult(action=Action.UNCHANGED, path=binary, detail=detail_cached)]

    module.ensure_binary(binary, required_version, bin_dir)
    return [ChangeResult(action=Action.CREATED, path=binary, detail=detail_cached)]


def _load_cq_binary(plugin_root: Path) -> ModuleType:
    """Load cq_binary.py from the plugin source tree as an isolated module."""
    cq_binary_path = plugin_root / CQ_BINARY_RELPATH
    if not cq_binary_path.exists():
        raise RuntimeError(f"cq_binary.py not found at {cq_binary_path}; is the plugin source tree intact?")
    spec = importlib.util.spec_from_file_location("cq_install._cq_binary", cq_binary_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load cq_binary.py from {cq_binary_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
