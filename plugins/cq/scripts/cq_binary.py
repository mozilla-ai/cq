"""Shared cq binary fetch and cache logic.

Stdlib-only module consumed by both `bootstrap.py` (when Claude launches
the MCP server) and the multi-host installer (`cq_install.binary`). It
owns the rules for where the binary is cached, how its version is
verified, and how it is fetched from GitHub releases when absent.

This module is run in two different environments: under whatever Python
Claude provides, and under the installer's uv-managed venv. It must
remain stdlib-only and must not import anything from the installer
package.
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO = "mozilla-ai/cq"


def check_version(binary: Path, required: str) -> bool:
    """Check whether the binary reports the required version."""
    return parse_version(binary) == required


def cq_binary_name() -> str:
    """Return the cq binary filename for the current platform."""
    return "cq.exe" if platform.system() == "Windows" else "cq"


def default_data_home() -> Path:
    """Return the default data home directory, respecting XDG_DATA_HOME.

    All platforms (Windows, macOS, Linux) honour XDG_DATA_HOME when it is
    set to an absolute path. Falls back to platform-appropriate locations
    otherwise.
    """
    system = platform.system()

    # Check XDG_DATA_HOME first on all platforms.
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home and Path(xdg_data_home).is_absolute():
        return Path(xdg_data_home)

    # Windows fallbacks.
    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data)
        app_data = os.environ.get("APPDATA")
        if app_data:
            return Path(app_data)
        return Path.home() / "AppData" / "Local"

    # Unix fallback (macOS, Linux, etc.).
    return Path.home() / ".local" / "share"


def download(version: str, system: str, bin_dir: Path, binary: Path) -> None:
    """Fetch the cq binary from GitHub releases for the current platform."""
    machine = platform.machine()
    arch_map: dict[str, str] = {
        "AMD64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "arm64",
        "aarch64": "aarch64",
    }
    arch = arch_map.get(machine)
    if not arch:
        print(f"Error: unsupported architecture: {machine}", file=sys.stderr)
        sys.exit(1)

    os_map: dict[str, str] = {"Darwin": "Darwin", "Linux": "Linux", "Windows": "Windows"}
    os_name = os_map.get(system)
    if not os_name:
        print(f"Error: unsupported OS: {system}", file=sys.stderr)
        sys.exit(1)

    tag = f"cli/v{version}"
    asset_base = f"cq_{os_name}_{arch}"

    if system == "Windows":
        url = f"https://github.com/{REPO}/releases/download/{tag}/{asset_base}.zip"
    else:
        url = f"https://github.com/{REPO}/releases/download/{tag}/{asset_base}.tar.gz"

    print(f"cq: downloading v{version} for {os_name}/{arch}...", file=sys.stderr)

    bin_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".archive") as tmp:
        tmp_path = Path(tmp.name)

    try:
        urllib.request.urlretrieve(url, tmp_path)

        if system == "Windows":
            with zipfile.ZipFile(tmp_path) as zf:
                zf.extract("cq.exe", bin_dir)
        else:
            with tarfile.open(tmp_path, "r:gz") as tf:
                tf.extract("cq", bin_dir)
            binary.chmod(0o755)
    finally:
        tmp_path.unlink(missing_ok=True)


def ensure_binary(binary: Path, required_version: str, bin_dir: Path) -> None:
    """Resolve the cq binary, preferring a cached copy over a fresh download."""
    # Fast path: cached binary (file or symlink) already at the right version.
    if binary.is_file() and check_version(binary, required_version):
        return

    # Discard any stale binary or broken symlink before resolving fresh.
    if binary.exists() or binary.is_symlink():
        binary.unlink()

    bin_dir.mkdir(parents=True, exist_ok=True)

    system_cq = shutil.which("cq")
    if system_cq and check_version(Path(system_cq), required_version):
        link_or_copy(Path(system_cq), binary)
        print(f"cq: using system v{required_version} from {system_cq}", file=sys.stderr)
        return

    download(required_version, platform.system(), bin_dir, binary)
    print(f"cq: downloaded v{required_version} to {binary}", file=sys.stderr)


def link_or_copy(source: Path, dest: Path) -> None:
    """Symlink on Unix, copy on Windows where symlinks need elevation."""
    dest.unlink(missing_ok=True)
    if platform.system() == "Windows":
        shutil.copy2(source, dest)
    else:
        dest.symlink_to(source)


def load_required_version(metadata_path: Path) -> str:
    """Return the required cq CLI version from bootstrap metadata."""
    if not metadata_path.exists():
        return ""
    with metadata_path.open() as f:
        config = json.load(f)
    return config.get("cli_version", "")


def parse_version(binary: Path) -> str:
    """Extract semver from 'cq --version' output."""
    try:
        output = subprocess.check_output(
            [str(binary), "--version"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        match = re.search(r"(\d+\.\d+\.\d+)", output)
        return match.group(1) if match else ""
    except (subprocess.SubprocessError, OSError):
        return ""


def runtime_root() -> Path:
    """Return shared runtime root used by every host integration."""
    return default_data_home() / "cq" / "runtime"


def shared_bin_dir() -> Path:
    """Return the shared runtime binary cache directory."""
    return runtime_root() / "bin"
