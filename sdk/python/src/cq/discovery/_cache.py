"""On-disk cache of resolved node discovery results.

Stores one JSON document per address, keyed by SHA-256 of the address
so that arbitrary URL characters never appear on disk.
Entries expire by file modification time plus a configured time-to-live (TTL).
Writes are atomic via temp-file plus rename so a crashed process never
leaves a half-written entry visible to the next invocation.

NOTE: instances are not safe for concurrent use across processes;
concurrent writers to the same address race on the final rename and
the last writer wins.
NOTE: constructing a Cache with `cache_dir=None` disables every cache operation
(get returns a miss, put and invalidate are no-ops) so callers can wire
a cache unconditionally and let configuration decide whether on-disk
persistence is active.
"""

import hashlib
import os
import tempfile
import time
from pathlib import Path

from pydantic import ValidationError

from ._types import NodeInfo
from ._validate import validate as _validate


class Cache:
    """Disk-backed cache mapping a node address to its resolved NodeInfo.

    Entries live as one JSON file per address under the configured directory.
    Freshness is determined by the file's modification time;
    entries older than the configured TTL are treated as misses.
    Schema-invalid or unreadable entries are also treated as misses and
    removed so the next read starts clean.
    """

    def __init__(self, cache_dir: Path | None, ttl_seconds: int) -> None:
        """Build a cache rooted at cache_dir with the given freshness time-to-live (TTL).

        A cache_dir of None disables the cache entirely;
        every cache operation becomes a no-op.
        The directory itself is created lazily on the first successful put
        so constructing a cache for a never-used address is free.
        """
        self._dir: Path | None = cache_dir
        self._ttl_seconds = ttl_seconds

    def get(self, addr: str) -> NodeInfo | None:
        """Return the cached NodeInfo for addr when a fresh, valid entry exists, otherwise None.

        An entry is fresh when its file modification time is within the configured TTL.
        Unreadable, expired, or schema-invalid entries are reported as a miss;
        invalid entries are also removed from disk so the next read is a
        clean miss rather than a repeated rejection.
        """
        if self._dir is None:
            return None
        path = self._dir / self._filename(addr)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None
        if (time.time() - mtime) > self._ttl_seconds:
            return None
        try:
            raw = path.read_bytes()
        except OSError:
            return None
        try:
            info = NodeInfo.model_validate_json(raw)
        except ValidationError:
            _remove_quiet(path)
            return None
        try:
            _validate(info)
        except ValueError:
            _remove_quiet(path)
            return None
        return info

    def invalidate(self, addr: str) -> None:
        """Remove the cache entry for addr if one exists.

        A missing entry is not an error.
        """
        if self._dir is None:
            return
        _remove_quiet(self._dir / self._filename(addr))

    def put(self, addr: str, info: NodeInfo) -> None:
        """Write info to disk as the cache entry for addr.

        The write is atomic:
        data is first written to a temp file in the cache directory and then
        renamed into place, so a partial write from a crashed process is never
        observable on the next read.
        NOTE: the temp file is created inside `cache_dir`, not the OS temp directory,
        so the write succeeds wherever the final write does (Windows, macOS, Linux)
        with no additional permission requirements.
        The cache directory is created if it does not already exist.
        """
        if self._dir is None:
            return
        self._dir.mkdir(parents=True, exist_ok=True)
        final_path = self._dir / self._filename(addr)
        # Open a temp file in the same directory so the rename stays on one filesystem.
        fd, tmp_name = tempfile.mkstemp(prefix="tmp-", suffix=".json", dir=self._dir)
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(info.model_dump_json().encode("utf-8"))
            tmp_path.replace(final_path)
        finally:
            _remove_quiet(tmp_path)

    def _filename(self, addr: str) -> str:
        """Return the on-disk filename for addr: lowercase SHA-256 hex plus .json."""
        return hashlib.sha256(addr.encode()).hexdigest() + ".json"


def _remove_quiet(path: Path) -> None:
    """Delete path if present; suppress FileNotFoundError so callers can treat removal as best-effort."""
    try:
        path.unlink()
    except FileNotFoundError:
        return
