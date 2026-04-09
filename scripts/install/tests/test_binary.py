"""Tests for cq_install.binary."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from cq_install.binary import ensure_cq_binary
from cq_install.context import Action

FAKE_CQ_BINARY = dedent(
    '''
    """Test stub for cq_binary.py that records calls into sibling sentinel files."""

    import json
    from pathlib import Path

    _MARKER_DIR = Path(__file__).resolve().parent.parent


    def load_required_version(metadata_path):
        if not metadata_path.exists():
            return ""
        with open(metadata_path) as f:
            return json.load(f).get("cli_version", "")


    def shared_bin_dir():
        return _MARKER_DIR / ".fake_bin"


    def cq_binary_name():
        return "cq"


    def check_version(binary, required):
        if not binary.is_file():
            return False
        return binary.read_text().strip() == required


    def ensure_binary(binary, required_version, bin_dir):
        bin_dir.mkdir(parents=True, exist_ok=True)
        binary.write_text(required_version)
        (_MARKER_DIR / ".ensure_called").write_text(
            f"{binary}|{required_version}|{bin_dir}"
        )
    '''
)


def _seed_plugin_tree(plugin_root: Path, *, cli_version: str | None = "0.2.0") -> None:
    scripts = plugin_root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    if cli_version is not None:
        (scripts / "bootstrap.json").write_text(f'{{"cli_version": "{cli_version}"}}\n')
    (scripts / "cq_binary.py").write_text(FAKE_CQ_BINARY)


def test_ensure_cq_binary_fetches_when_missing(tmp_path):
    plugin_root = tmp_path / "plugins" / "cq"
    _seed_plugin_tree(plugin_root)

    results = ensure_cq_binary(plugin_root)

    assert len(results) == 1
    assert results[0].action == Action.CREATED
    assert "cq v0.2.0" in results[0].detail
    assert (plugin_root / ".fake_bin" / "cq").read_text() == "0.2.0"
    assert (plugin_root / ".ensure_called").exists()


def test_ensure_cq_binary_is_unchanged_when_already_valid(tmp_path):
    plugin_root = tmp_path / "plugins" / "cq"
    _seed_plugin_tree(plugin_root)
    fake_bin = plugin_root / ".fake_bin"
    fake_bin.mkdir()
    (fake_bin / "cq").write_text("0.2.0")

    results = ensure_cq_binary(plugin_root)

    assert len(results) == 1
    assert results[0].action == Action.UNCHANGED
    assert "cq v0.2.0" in results[0].detail
    assert not (plugin_root / ".ensure_called").exists()


def test_ensure_cq_binary_dry_run_skips_fetch_when_missing(tmp_path):
    plugin_root = tmp_path / "plugins" / "cq"
    _seed_plugin_tree(plugin_root)

    results = ensure_cq_binary(plugin_root, dry_run=True)

    assert len(results) == 1
    assert results[0].action == Action.SKIPPED
    assert "would fetch cq v0.2.0" in results[0].detail
    assert not (plugin_root / ".fake_bin").exists()
    assert not (plugin_root / ".ensure_called").exists()


def test_ensure_cq_binary_dry_run_is_unchanged_when_already_valid(tmp_path):
    plugin_root = tmp_path / "plugins" / "cq"
    _seed_plugin_tree(plugin_root)
    fake_bin = plugin_root / ".fake_bin"
    fake_bin.mkdir()
    (fake_bin / "cq").write_text("0.2.0")

    results = ensure_cq_binary(plugin_root, dry_run=True)

    assert len(results) == 1
    assert results[0].action == Action.UNCHANGED


def test_ensure_cq_binary_raises_when_cq_binary_missing(tmp_path):
    plugin_root = tmp_path / "plugins" / "cq"
    (plugin_root / "scripts").mkdir(parents=True)
    (plugin_root / "scripts" / "bootstrap.json").write_text('{"cli_version": "0.2.0"}\n')

    with pytest.raises(RuntimeError, match="cq_binary.py"):
        ensure_cq_binary(plugin_root)


def test_ensure_cq_binary_raises_when_version_missing(tmp_path):
    plugin_root = tmp_path / "plugins" / "cq"
    _seed_plugin_tree(plugin_root, cli_version=None)

    with pytest.raises(RuntimeError, match="cli_version"):
        ensure_cq_binary(plugin_root)
