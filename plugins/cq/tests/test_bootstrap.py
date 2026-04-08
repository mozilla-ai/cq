"""Tests for plugins/cq/scripts/bootstrap.py path resolution."""

from __future__ import annotations

from importlib import util
from pathlib import Path

BOOTSTRAP_PATH = Path(__file__).resolve().parent.parent / "scripts" / "bootstrap.py"


def _load_bootstrap_module():
    spec = util.spec_from_file_location("cq_bootstrap", BOOTSTRAP_PATH)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_data_home_uses_xdg_data_home_on_linux(monkeypatch):
    module = _load_bootstrap_module()
    monkeypatch.setattr(module.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg-data")
    assert module.default_data_home() == Path("/tmp/xdg-data")


def test_default_data_home_falls_back_on_linux(monkeypatch):
    module = _load_bootstrap_module()
    monkeypatch.setattr(module.platform, "system", lambda: "Linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(module.Path, "home", lambda: Path("/home/tester"))
    assert module.default_data_home() == Path("/home/tester/.local/share")


def test_default_data_home_uses_xdg_data_home_on_macos(monkeypatch):
    module = _load_bootstrap_module()
    monkeypatch.setattr(module.platform, "system", lambda: "Darwin")
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg-data")
    assert module.default_data_home() == Path("/tmp/xdg-data")


def test_default_data_home_falls_back_on_macos(monkeypatch):
    module = _load_bootstrap_module()
    monkeypatch.setattr(module.platform, "system", lambda: "Darwin")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(module.Path, "home", lambda: Path("/Users/tester"))
    assert module.default_data_home() == Path("/Users/tester/.local/share")


def test_default_data_home_prefers_localappdata_on_windows(monkeypatch):
    module = _load_bootstrap_module()
    monkeypatch.setattr(module.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\tester\AppData\Local")
    monkeypatch.setenv("APPDATA", r"C:\Users\tester\AppData\Roaming")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert module.default_data_home() == Path(r"C:\Users\tester\AppData\Local")


def test_load_required_version_prefers_neutral_bootstrap_metadata(monkeypatch, tmp_path):
    module = _load_bootstrap_module()
    bootstrap_metadata = BOOTSTRAP_PATH.with_name("bootstrap.json")
    original = bootstrap_metadata.read_text() if bootstrap_metadata.exists() else None
    try:
        bootstrap_metadata.write_text('{"cli_version": "9.9.9"}\n')
        assert module.load_required_version() == "9.9.9"
    finally:
        if original is None:
            bootstrap_metadata.unlink(missing_ok=True)
        else:
            bootstrap_metadata.write_text(original)


def test_load_required_version_returns_empty_when_metadata_missing():
    bootstrap_metadata = BOOTSTRAP_PATH.with_name("bootstrap.json")
    original = bootstrap_metadata.read_text() if bootstrap_metadata.exists() else None
    try:
        bootstrap_metadata.unlink(missing_ok=True)
        module = _load_bootstrap_module()
        assert module.load_required_version() == ""
    finally:
        if original is not None:
            bootstrap_metadata.write_text(original)


def test_shared_bin_dir_is_under_runtime_root(monkeypatch):
    module = _load_bootstrap_module()
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg-data")
    assert module.shared_bin_dir() == Path("/tmp/xdg-data/cq/runtime/bin")


def test_ensure_binary_reuses_valid_symlink(monkeypatch, tmp_path):
    module = _load_bootstrap_module()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)

    system_binary = tmp_path / "system-cq"
    system_binary.write_text("fake")
    binary = bin_dir / "cq"
    binary.symlink_to(system_binary)

    monkeypatch.setattr(module, "check_version", lambda _binary, _required: True)
    monkeypatch.setattr(module.shutil, "which", lambda _name: None)

    def _download_should_not_run(*_args, **_kwargs):
        raise AssertionError("download should not run for valid cached symlink")

    monkeypatch.setattr(module, "download", _download_should_not_run)

    module.ensure_binary(binary, "0.2.0", "Linux", bin_dir)

    assert binary.is_symlink()
    assert binary.resolve() == system_binary.resolve()
