#!/usr/bin/env python3
"""Bootstrap the cq MCP server.

Ensures the cq binary is available, then replaces this process with
'cq mcp' so the host talks directly to the Go MCP server over stdio.

Resolves the binary from: a local copy in bin/, the system PATH, or
a GitHub release download. Cross-platform (macOS, Linux, Windows),
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


def main():
    """Ensure the cq binary is available, then exec into the MCP server."""
    plugin_root = Path(__file__).resolve().parent.parent
    plugin_json = plugin_root / ".claude-plugin" / "plugin.json"
    bin_dir = plugin_root / "bin"

    with plugin_json.open() as f:
        config = json.load(f)

    required_version = config.get("cliVersion")
    if not required_version:
        print("Error: cliVersion not set in plugin.json", file=sys.stderr)
        sys.exit(1)

    system = platform.system()
    ext = ".exe" if system == "Windows" else ""
    binary = bin_dir / f"cq{ext}"

    ensure_binary(binary, required_version, system, bin_dir)

    os.execvp(str(binary), [str(binary), "mcp"])


def ensure_binary(binary, required_version, system, bin_dir):
    """Resolve the cq binary, preferring a cached copy over a fresh download."""
    # Fast path: a real binary (not a symlink) already at the right version.
    if binary.is_file() and not binary.is_symlink() and check_version(binary, required_version):
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


def parse_version(binary):
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


def check_version(binary, required):
    """Check whether the binary reports the required version."""
    return parse_version(binary) == required


def link_or_copy(source, dest):
    """Symlink on Unix, copy on Windows where symlinks need elevation."""
    dest.unlink(missing_ok=True)
    if platform.system() == "Windows":
        shutil.copy2(source, dest)
    else:
        dest.symlink_to(source)


def download(version, system, bin_dir, binary):
    """Fetch the cq binary from GitHub releases for the current platform."""
    machine = platform.machine()
    arch_map = {"AMD64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "aarch64"}
    arch = arch_map.get(machine)
    if not arch:
        print(f"Error: unsupported architecture: {machine}", file=sys.stderr)
        sys.exit(1)

    os_map = {"Darwin": "Darwin", "Linux": "Linux", "Windows": "Windows"}
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
