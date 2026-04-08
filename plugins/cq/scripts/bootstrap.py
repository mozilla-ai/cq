#!/usr/bin/env python3
"""Bootstrap the cq MCP server.

Ensures the cq binary is available, then replaces this process with
'cq mcp' so the host talks directly to the Go MCP server over stdio.

Resolves the binary from: a shared per-user runtime bin cache, the
system PATH, or a GitHub release download. Cross-platform (macOS,
Linux, Windows),
stdlib only.
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


def main() -> None:
    """Ensure the cq binary is available, then exec into the MCP server."""
    bin_dir = shared_bin_dir()

    required_version = load_required_version()
    if not required_version:
        print("Error: required CLI version not set in bootstrap metadata", file=sys.stderr)
        sys.exit(1)

    system = platform.system()
    ext = ".exe" if system == "Windows" else ""
    binary = bin_dir / f"cq{ext}"

    ensure_binary(binary, required_version, system, bin_dir)

    os.execvp(str(binary), [str(binary), "mcp"])


def ensure_binary(binary: Path, required_version: str, system: str, bin_dir: Path) -> None:
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

    download(required_version, system, bin_dir, binary)
    print(f"cq: downloaded v{required_version} to {binary}", file=sys.stderr)


def default_data_home() -> Path:
    """Return the default data home directory, respecting XDG_DATA_HOME.

    All platforms (Windows, macOS, Linux) support XDG_DATA_HOME.
    Falls back to platform default if XDG_DATA_HOME is not set or relative.
    """
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


def load_required_version() -> str:
    """Return the required cq CLI version from bootstrap metadata."""
    metadata_path = Path(__file__).resolve().with_name("bootstrap.json")
    if not metadata_path.exists():
        return ""
    with metadata_path.open() as f:
        config = json.load(f)
    return config.get("cli_version", "")


def runtime_root() -> Path:
    """Return shared runtime root used by every host integration."""
    return default_data_home() / "cq" / "runtime"


def shared_bin_dir() -> Path:
    """Return the shared runtime binary cache directory."""
    return runtime_root() / "bin"


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


def check_version(binary: Path, required: str) -> bool:
    """Check whether the binary reports the required version."""
    return parse_version(binary) == required


def link_or_copy(source: Path, dest: Path) -> None:
    """Symlink on Unix, copy on Windows where symlinks need elevation."""
    dest.unlink(missing_ok=True)
    if platform.system() == "Windows":
        shutil.copy2(source, dest)
    else:
        dest.symlink_to(source)


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


if __name__ == "__main__":
    main()
