"""Shared pytest fixtures for the plugin tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

HOOK_PATH = Path(__file__).resolve().parent.parent / "hooks" / "cursor" / "cq_cursor_hook.py"


@pytest.fixture(scope="session")
def hook() -> ModuleType:
    """Load cq_cursor_hook.py as a module once per test session.

    The hook script is not a package member so can't be imported directly; we
    use importlib.util to load it by path. The module has no mutable state
    between tests (each test uses a fresh tmp_path for state files), so a
    session-scoped fixture is safe and cheap.
    """
    spec = importlib.util.spec_from_file_location("cq_cursor_hook", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["cq_cursor_hook"] = module
    spec.loader.exec_module(module)
    return module
