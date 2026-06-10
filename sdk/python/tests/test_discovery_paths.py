"""Tests for the XDG-compliant discovery cache directory resolver."""

import logging
from pathlib import Path

import pytest

from cq.discovery._paths import default_cache_dir


class TestDefaultCacheDir:
    def test_xdg_cache_home_takes_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", "/custom/xdg")
        monkeypatch.setenv("HOME", "/home/user")
        assert default_cache_dir() == Path("/custom/xdg/cq/discovery")

    def test_falls_back_to_home_when_xdg_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        monkeypatch.setenv("HOME", "/home/user")
        assert default_cache_dir() == Path("/home/user/.cache/cq/discovery")

    def test_returns_none_when_xdg_and_home_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        monkeypatch.delenv("HOME", raising=False)
        assert default_cache_dir() is None

    def test_empty_xdg_falls_through_to_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", "")
        monkeypatch.setenv("HOME", "/home/user")
        assert default_cache_dir() == Path("/home/user/.cache/cq/discovery")

    def test_whitespace_xdg_falls_through_to_home_without_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", "   ")
        monkeypatch.setenv("HOME", "/home/user")
        with caplog.at_level(logging.WARNING, logger="cq.discovery"):
            result = default_cache_dir()
        assert result == Path("/home/user/.cache/cq/discovery")
        assert caplog.records == []

    def test_relative_xdg_returns_none_and_warns(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", "relative/path")
        monkeypatch.setenv("HOME", "/home/user")
        with caplog.at_level(logging.WARNING, logger="cq.discovery"):
            result = default_cache_dir()
        assert result is None
        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.WARNING
        assert "absolute path" in caplog.records[0].getMessage()
        assert "relative/path" in caplog.records[0].getMessage()

    def test_absolute_xdg_returns_subdirectory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", "/absolute/path")
        monkeypatch.setenv("HOME", "/home/user")
        assert default_cache_dir() == Path("/absolute/path") / "cq" / "discovery"
