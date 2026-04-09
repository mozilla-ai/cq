"""Read and write copy_tree manifests."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

MANIFEST_VERSION = 1


def hash_file(path: Path) -> str:
    """Return the hex sha256 of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path) -> dict | None:
    """Return the parsed manifest dict, or None if missing or unreadable."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("version") != MANIFEST_VERSION:
        return None
    return data


def write_manifest(path: Path, files: list[dict]) -> None:
    """Write a fresh manifest covering the given (relative path, sha256) entries."""
    payload = {
        "version": MANIFEST_VERSION,
        "installed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": files,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
