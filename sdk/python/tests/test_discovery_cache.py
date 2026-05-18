"""Tests for the on-disk discovery cache."""

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from cq.discovery._cache import Cache
from cq.discovery._types import DEFAULT_CACHE_TTL_SECONDS, NodeInfo


def _make_info(**overrides: object) -> NodeInfo:
    defaults: dict[str, object] = {
        "version": 1,
        "api_base_url": "https://node.example.com/api/v1",
        "api_version": "v1",
    }
    return NodeInfo(**(defaults | overrides))  # type: ignore[arg-type]  # pydantic kwarg widening


@pytest.fixture()
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "discovery-cache"


class TestGet:
    def test_returns_none_for_unknown_addr(self, cache_dir: Path) -> None:
        cache = Cache(cache_dir=cache_dir, ttl_seconds=DEFAULT_CACHE_TTL_SECONDS)
        assert cache.get("https://unknown.example.com") is None

    def test_returns_hit_within_ttl(self, cache_dir: Path) -> None:
        cache = Cache(cache_dir=cache_dir, ttl_seconds=60)
        info = _make_info()
        cache.put("https://node.example.com", info)
        assert cache.get("https://node.example.com") == info

    def test_returns_none_after_ttl(self, cache_dir: Path) -> None:
        cache = Cache(cache_dir=cache_dir, ttl_seconds=60)
        info = _make_info()
        addr = "https://node.example.com"
        cache.put(addr, info)
        # Backdate mtime past the TTL.
        path = cache_dir / (cache._filename(addr))
        old = time.time() - 120
        os.utime(path, (old, old))
        assert cache.get(addr) is None


class TestInvalidate:
    def test_removes_existing_entry(self, cache_dir: Path) -> None:
        cache = Cache(cache_dir=cache_dir, ttl_seconds=60)
        addr = "https://node.example.com"
        cache.put(addr, _make_info())
        cache.invalidate(addr)
        assert cache.get(addr) is None
        assert not (cache_dir / cache._filename(addr)).exists()

    def test_missing_entry_is_noop(self, cache_dir: Path) -> None:
        cache = Cache(cache_dir=cache_dir, ttl_seconds=60)
        # Must not raise.
        cache.invalidate("https://never-written.example.com")


class TestPut:
    def test_leaves_no_temp_files(self, cache_dir: Path) -> None:
        cache = Cache(cache_dir=cache_dir, ttl_seconds=60)
        cache.put("https://node.example.com", _make_info())
        # The only file in the cache dir is the final entry.
        entries = list(cache_dir.iterdir())
        assert len(entries) == 1
        assert entries[0].name.endswith(".json")
        assert not entries[0].name.startswith("tmp")

    def test_creates_directory_lazily(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "does-not-exist-yet"
        cache = Cache(cache_dir=cache_dir, ttl_seconds=60)
        assert not cache_dir.exists()
        cache.put("https://node.example.com", _make_info())
        assert cache_dir.is_dir()

    def test_write_failure_leaves_no_temp_files(self, cache_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """If serialization fails mid-write, no temp file may remain."""
        cache = Cache(cache_dir=cache_dir, ttl_seconds=60)

        def boom(self: object) -> str:
            raise RuntimeError("encode failure injected by test")

        monkeypatch.setattr(NodeInfo, "model_dump_json", boom)
        with pytest.raises(RuntimeError, match="encode failure injected by test"):
            cache.put("https://node.example.com", _make_info())
        # Directory may or may not exist; if it does, no temp residue.
        if cache_dir.exists():
            assert list(cache_dir.iterdir()) == []

    def test_rename_failure_leaves_no_temp_files(self, cache_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """If the final rename fails, the exception propagates and no temp file remains."""
        cache = Cache(cache_dir=cache_dir, ttl_seconds=60)

        def boom(self: Path, target: object) -> Path:
            raise OSError("rename failure injected by test")

        monkeypatch.setattr(Path, "replace", boom)
        with pytest.raises(OSError, match="rename failure injected by test"):
            cache.put("https://node.example.com", _make_info())
        assert list(cache_dir.iterdir()) == []


class TestSchemaInvalidEntry:
    def test_schema_invalid_stored_entry_is_miss_and_removed(self, cache_dir: Path) -> None:
        """A cached file that does not parse as NodeInfo is treated as a miss and deleted."""
        cache = Cache(cache_dir=cache_dir, ttl_seconds=60)
        addr = "https://node.example.com"
        path = cache_dir / cache._filename(addr)
        cache_dir.mkdir(parents=True, exist_ok=True)
        # Write a syntactically valid but schema-invalid entry (empty api_base_url).
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "api_base_url": "",
                    "api_version": "v1",
                }
            )
        )
        assert cache.get(addr) is None
        assert not path.exists()

    def test_unknown_field_stored_entry_is_miss_and_removed(self, cache_dir: Path) -> None:
        """A cached file with unknown JSON fields is treated as a miss and deleted."""
        cache = Cache(cache_dir=cache_dir, ttl_seconds=60)
        addr = "https://node.example.com"
        path = cache_dir / cache._filename(addr)
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "api_base_url": "https://node.example.com/api/v1",
                    "api_version": "v1",
                    "unexpected_field": "boom",
                }
            )
        )
        assert cache.get(addr) is None
        assert not path.exists()

    def test_wrong_discovery_version_is_miss_and_removed(self, cache_dir: Path) -> None:
        cache = Cache(cache_dir=cache_dir, ttl_seconds=60)
        addr = "https://node.example.com"
        path = cache_dir / cache._filename(addr)
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "version": 99,
                    "api_base_url": "https://node.example.com/api/v1",
                    "api_version": "v1",
                }
            )
        )
        assert cache.get(addr) is None
        assert not path.exists()

    def test_wrong_api_version_is_miss_and_removed(self, cache_dir: Path) -> None:
        cache = Cache(cache_dir=cache_dir, ttl_seconds=60)
        addr = "https://node.example.com"
        path = cache_dir / cache._filename(addr)
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "api_base_url": "https://node.example.com/api/v1",
                    "api_version": "v99",
                }
            )
        )
        assert cache.get(addr) is None
        assert not path.exists()

    def test_non_http_scheme_is_miss_and_removed(self, cache_dir: Path) -> None:
        cache = Cache(cache_dir=cache_dir, ttl_seconds=60)
        addr = "https://node.example.com"
        path = cache_dir / cache._filename(addr)
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "api_base_url": "ftp://node.example.com/api/v1",
                    "api_version": "v1",
                }
            )
        )
        assert cache.get(addr) is None
        assert not path.exists()


class TestDisabledCache:
    """Cache(cache_dir=None) is a no-op on every operation."""

    def test_get_returns_none(self) -> None:
        cache = Cache(cache_dir=None, ttl_seconds=60)
        assert cache.get("https://node.example.com") is None

    def test_put_does_not_invoke_filesystem(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*args: object, **kwargs: object) -> tuple[int, str]:
            raise AssertionError("mkstemp must not be called when disabled")

        monkeypatch.setattr(tempfile, "mkstemp", boom)
        Cache(cache_dir=None, ttl_seconds=60).put("https://node.example.com", _make_info())

    def test_invalidate_does_not_invoke_filesystem(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(self: Path) -> None:
            raise AssertionError("unlink must not be called when disabled")

        monkeypatch.setattr(Path, "unlink", boom)
        Cache(cache_dir=None, ttl_seconds=60).invalidate("https://node.example.com")


class TestFilename:
    def test_filename_is_sha256_hex_json(self, cache_dir: Path) -> None:
        """The filename must be deterministic SHA-256 hex of the address plus .json."""
        cache = Cache(cache_dir=cache_dir, ttl_seconds=60)
        addr = "https://node.example.com"
        expected = hashlib.sha256(addr.encode()).hexdigest() + ".json"
        assert cache._filename(addr) == expected
