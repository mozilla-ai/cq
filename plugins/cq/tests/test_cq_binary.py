"""Tests for plugins/cq/scripts/cq_binary.py."""

from __future__ import annotations

from importlib import util
from pathlib import Path
from types import ModuleType

import pytest

CQ_BINARY_PATH = Path(__file__).resolve().parent.parent / "scripts" / "cq_binary.py"


def _load_cq_binary() -> ModuleType:
    """Load cq_binary.py as an isolated module for testing."""
    spec = util.spec_from_file_location("cq_binary_under_test", CQ_BINARY_PATH)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cq_binary() -> ModuleType:
    return _load_cq_binary()


def test_default_data_home_uses_xdg_data_home_on_linux(cq_binary, monkeypatch):
    monkeypatch.setattr(cq_binary.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg-data")
    assert cq_binary.default_data_home() == Path("/tmp/xdg-data")


def test_default_data_home_falls_back_on_linux(cq_binary, monkeypatch):
    monkeypatch.setattr(cq_binary.platform, "system", lambda: "Linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(cq_binary.Path, "home", lambda: Path("/home/tester"))
    assert cq_binary.default_data_home() == Path("/home/tester/.local/share")


def test_default_data_home_uses_xdg_data_home_on_macos(cq_binary, monkeypatch):
    monkeypatch.setattr(cq_binary.platform, "system", lambda: "Darwin")
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg-data")
    assert cq_binary.default_data_home() == Path("/tmp/xdg-data")


def test_default_data_home_falls_back_on_macos(cq_binary, monkeypatch):
    monkeypatch.setattr(cq_binary.platform, "system", lambda: "Darwin")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(cq_binary.Path, "home", lambda: Path("/Users/tester"))
    assert cq_binary.default_data_home() == Path("/Users/tester/.local/share")


def test_default_data_home_prefers_localappdata_on_windows(cq_binary, monkeypatch):
    monkeypatch.setattr(cq_binary.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\tester\AppData\Local")
    monkeypatch.setenv("APPDATA", r"C:\Users\tester\AppData\Roaming")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert cq_binary.default_data_home() == Path(r"C:\Users\tester\AppData\Local")


def test_default_data_home_falls_back_to_appdata_on_windows(cq_binary, monkeypatch):
    monkeypatch.setattr(cq_binary.platform, "system", lambda: "Windows")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("APPDATA", r"C:\Users\tester\AppData\Roaming")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert cq_binary.default_data_home() == Path(r"C:\Users\tester\AppData\Roaming")


def test_runtime_root_is_under_data_home(cq_binary, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg-data")
    assert cq_binary.runtime_root() == Path("/tmp/xdg-data/cq/runtime")


def test_shared_bin_dir_is_under_runtime_root(cq_binary, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg-data")
    assert cq_binary.shared_bin_dir() == Path("/tmp/xdg-data/cq/runtime/bin")


def test_cq_binary_name_on_windows(cq_binary, monkeypatch):
    monkeypatch.setattr(cq_binary.platform, "system", lambda: "Windows")
    assert cq_binary.cq_binary_name() == "cq.exe"


def test_cq_binary_name_on_unix(cq_binary, monkeypatch):
    monkeypatch.setattr(cq_binary.platform, "system", lambda: "Linux")
    assert cq_binary.cq_binary_name() == "cq"


def test_load_required_version_reads_cli_version(cq_binary, tmp_path):
    metadata = tmp_path / "bootstrap.json"
    metadata.write_text('{"cli_version": "9.9.9"}\n')
    assert cq_binary.load_required_version(metadata) == "9.9.9"


def test_load_required_version_returns_empty_when_missing_file(cq_binary, tmp_path):
    metadata = tmp_path / "bootstrap.json"
    assert cq_binary.load_required_version(metadata) == ""


def test_load_required_version_returns_empty_when_missing_key(cq_binary, tmp_path):
    metadata = tmp_path / "bootstrap.json"
    metadata.write_text('{"other": "value"}\n')
    assert cq_binary.load_required_version(metadata) == ""


def test_check_version_returns_true_on_match(cq_binary, monkeypatch):
    monkeypatch.setattr(cq_binary, "parse_version", lambda _binary: "1.2.3")
    assert cq_binary.check_version(Path("/fake/cq"), "1.2.3") is True


def test_check_version_returns_false_on_mismatch(cq_binary, monkeypatch):
    monkeypatch.setattr(cq_binary, "parse_version", lambda _binary: "1.2.3")
    assert cq_binary.check_version(Path("/fake/cq"), "9.9.9") is False


def test_ensure_binary_fast_path_leaves_existing_binary_alone(cq_binary, monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    binary = bin_dir / "cq"
    binary.write_text("existing")

    monkeypatch.setattr(cq_binary, "check_version", lambda _b, _v: True)

    def _download_should_not_run(*_args, **_kwargs):
        raise AssertionError("download should not run on fast path")

    monkeypatch.setattr(cq_binary, "download", _download_should_not_run)
    monkeypatch.setattr(cq_binary.shutil, "which", lambda _name: None)

    cq_binary.ensure_binary(binary, "0.2.0", bin_dir)

    assert binary.read_text() == "existing"


def test_ensure_binary_reuses_valid_symlink(cq_binary, monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    system_binary = tmp_path / "system-cq"
    system_binary.write_text("fake")
    binary = bin_dir / "cq"
    binary.symlink_to(system_binary)

    monkeypatch.setattr(cq_binary, "check_version", lambda _b, _v: True)
    monkeypatch.setattr(cq_binary.shutil, "which", lambda _name: None)

    def _download_should_not_run(*_args, **_kwargs):
        raise AssertionError("download should not run for valid cached symlink")

    monkeypatch.setattr(cq_binary, "download", _download_should_not_run)

    cq_binary.ensure_binary(binary, "0.2.0", bin_dir)

    assert binary.is_symlink()
    assert binary.resolve() == system_binary.resolve()


def test_ensure_binary_falls_back_to_system_cq(cq_binary, monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    binary = bin_dir / "cq"

    system_binary = tmp_path / "usr-local-bin-cq"
    system_binary.write_text("real")

    monkeypatch.setattr(cq_binary, "check_version", lambda _b, _v: True)
    monkeypatch.setattr(cq_binary.shutil, "which", lambda _name: str(system_binary))

    def _download_should_not_run(*_args, **_kwargs):
        raise AssertionError("download should not run when system cq is valid")

    monkeypatch.setattr(cq_binary, "download", _download_should_not_run)

    cq_binary.ensure_binary(binary, "0.2.0", bin_dir)

    assert binary.exists()
    assert binary.resolve() == system_binary.resolve()


def test_ensure_binary_downloads_when_no_system_cq(cq_binary, monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    binary = bin_dir / "cq"

    monkeypatch.setattr(cq_binary, "check_version", lambda _b, _v: False)
    monkeypatch.setattr(cq_binary.shutil, "which", lambda _name: None)
    monkeypatch.setattr(cq_binary.platform, "system", lambda: "Linux")

    called_with: dict = {}

    def _fake_download(version, system, caller_bin_dir, caller_binary):
        called_with["version"] = version
        called_with["system"] = system
        called_with["bin_dir"] = caller_bin_dir
        called_with["binary"] = caller_binary
        caller_bin_dir.mkdir(parents=True, exist_ok=True)
        caller_binary.write_text("downloaded")

    monkeypatch.setattr(cq_binary, "download", _fake_download)

    cq_binary.ensure_binary(binary, "0.2.0", bin_dir)

    assert called_with == {
        "version": "0.2.0",
        "system": "Linux",
        "bin_dir": bin_dir,
        "binary": binary,
    }


def test_ensure_binary_unlinks_broken_symlink_before_resolving(cq_binary, monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    binary = bin_dir / "cq"
    binary.symlink_to(tmp_path / "does-not-exist")

    real_cq = tmp_path / "real-cq"
    real_cq.write_text("real")

    monkeypatch.setattr(cq_binary, "check_version", lambda _b, _v: True)
    monkeypatch.setattr(cq_binary.shutil, "which", lambda _name: str(real_cq))
    monkeypatch.setattr(cq_binary, "download", lambda *_a, **_k: None)

    cq_binary.ensure_binary(binary, "0.2.0", bin_dir)

    assert binary.exists()
    assert binary.resolve() == real_cq.resolve()
