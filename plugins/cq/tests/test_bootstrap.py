"""Smoke test for plugins/cq/scripts/bootstrap.py.

The fetch/cache logic lives in `cq_binary.py` and is covered by
`test_cq_binary.py`. This file only verifies that `bootstrap.main()`
wires the two together in the expected order.
"""

from __future__ import annotations

import sys
from importlib import util
from pathlib import Path
from types import ModuleType

import pytest

BOOTSTRAP_PATH = Path(__file__).resolve().parent.parent / "scripts" / "bootstrap.py"
SCRIPTS_DIR = BOOTSTRAP_PATH.parent


def _load_bootstrap() -> ModuleType:
    """Load bootstrap.py with the scripts dir on sys.path for cq_binary import."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = util.spec_from_file_location("cq_bootstrap_under_test", BOOTSTRAP_PATH)
        assert spec is not None and spec.loader is not None
        module = util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_main_loads_version_ensures_binary_and_replaces_process(monkeypatch, tmp_path):
    metadata = tmp_path / "bootstrap.json"
    metadata.write_text('{"cli_version": "0.2.0"}\n')

    bootstrap = _load_bootstrap()
    calls: list[tuple[str, tuple]] = []

    monkeypatch.setattr(
        bootstrap,
        "__file__",
        str(metadata.parent / "bootstrap.py"),
    )
    monkeypatch.setattr(bootstrap.cq_binary, "shared_bin_dir", lambda: tmp_path / "bin")
    monkeypatch.setattr(bootstrap.cq_binary, "cq_binary_name", lambda: "cq")

    def _fake_ensure(binary, required, bin_dir):
        calls.append(("ensure", (binary, required, bin_dir)))

    def _fake_replace(path, argv):
        calls.append(("replace", (path, tuple(argv))))
        raise SystemExit(0)

    monkeypatch.setattr(bootstrap.cq_binary, "ensure_binary", _fake_ensure)
    monkeypatch.setattr(bootstrap.os, "execvp", _fake_replace)

    with pytest.raises(SystemExit) as exc_info:
        bootstrap.main()

    assert exc_info.value.code == 0
    assert calls == [
        ("ensure", (tmp_path / "bin" / "cq", "0.2.0", tmp_path / "bin")),
        ("replace", (str(tmp_path / "bin" / "cq"), (str(tmp_path / "bin" / "cq"), "mcp"))),
    ]


def test_main_exits_when_metadata_missing_version(monkeypatch, tmp_path, capsys):
    metadata = tmp_path / "bootstrap.json"
    metadata.write_text("{}\n")

    bootstrap = _load_bootstrap()
    monkeypatch.setattr(
        bootstrap,
        "__file__",
        str(metadata.parent / "bootstrap.py"),
    )

    with pytest.raises(SystemExit) as exc_info:
        bootstrap.main()

    assert exc_info.value.code == 1
    assert "required CLI version not set" in capsys.readouterr().err
