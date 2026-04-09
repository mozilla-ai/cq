"""Shared runtime path helpers for installer-managed cq assets."""

from __future__ import annotations

import os
from pathlib import Path


def runtime_root() -> Path:
    """Return the shared runtime root used by all host integrations.

    Respects XDG_DATA_HOME on all platforms per XDG Base Directory spec.
    """
    return _default_data_home() / "cq" / "runtime"


def _default_data_home() -> Path:
    """Return the default data home directory, respecting XDG_DATA_HOME.

    All platforms (Windows, macOS, Linux) support XDG_DATA_HOME.
    Falls back to platform default if XDG_DATA_HOME is not set or relative.
    """
    import platform

    system = platform.system()

    # Check XDG_DATA_HOME first on all platforms
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home and Path(xdg_data_home).is_absolute():
        return Path(xdg_data_home)

    # Windows fallbacks
    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data)
        app_data = os.environ.get("APPDATA")
        if app_data:
            return Path(app_data)
        return Path.home() / "AppData" / "Local"

    # Unix fallback (macOS, Linux, etc.)
    return Path.home() / ".local" / "share"
