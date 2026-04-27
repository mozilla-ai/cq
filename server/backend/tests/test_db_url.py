"""Tests for resolve_database_url()."""

from pathlib import Path

import pytest

from cq_server.db_url import resolve_database_url, resolve_sqlite_db_path


def test_explicit_database_url_wins(monkeypatch):
    monkeypatch.setenv("CQ_DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setenv("CQ_DB_PATH", "/tmp/ignored.db")
    assert resolve_database_url() == "postgresql://u:p@h/d"


def test_db_path_becomes_sqlite_url(monkeypatch, tmp_path):
    monkeypatch.delenv("CQ_DATABASE_URL", raising=False)
    db = tmp_path / "cq.db"
    monkeypatch.setenv("CQ_DB_PATH", str(db))
    assert resolve_database_url() == f"sqlite:///{db}"


def test_default_when_nothing_set(monkeypatch):
    monkeypatch.delenv("CQ_DATABASE_URL", raising=False)
    monkeypatch.delenv("CQ_DB_PATH", raising=False)
    assert resolve_database_url() == "sqlite:////data/cq.db"


def test_empty_database_url_falls_through(monkeypatch, tmp_path):
    # Container orchestrators sometimes pass empty env vars; treat the same
    # as unset so CQ_DB_PATH still wins.
    db = tmp_path / "cq.db"
    monkeypatch.setenv("CQ_DATABASE_URL", "")
    monkeypatch.setenv("CQ_DB_PATH", str(db))
    assert resolve_database_url() == f"sqlite:///{db}"


class TestResolveSqliteDbPath:
    """``resolve_sqlite_db_path`` is the single source of truth for both the
    migration URL and the runtime store's filesystem path during the
    rollout window. Any divergence here is a footgun: migrations would
    target one DB while the server reads/writes another.
    """

    def test_returns_url_and_path_for_cq_db_path(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CQ_DATABASE_URL", raising=False)
        db = tmp_path / "cq.db"
        monkeypatch.setenv("CQ_DB_PATH", str(db))

        url, path = resolve_sqlite_db_path()

        assert url == f"sqlite:///{db}"
        assert path == db

    def test_cq_database_url_governs_both_url_and_path(self, monkeypatch, tmp_path):
        winning = tmp_path / "winning.db"
        losing = tmp_path / "losing.db"
        monkeypatch.setenv("CQ_DATABASE_URL", f"sqlite:///{winning}")
        monkeypatch.setenv("CQ_DB_PATH", str(losing))

        url, path = resolve_sqlite_db_path()

        # Migration URL and runtime path agree — they both target the
        # CQ_DATABASE_URL DB, never the CQ_DB_PATH one.
        assert url == f"sqlite:///{winning}"
        assert path == winning

    def test_non_sqlite_url_is_rejected(self, monkeypatch):
        monkeypatch.setenv("CQ_DATABASE_URL", "postgresql+psycopg://u:p@h/d")

        with pytest.raises(RuntimeError, match="SQLite"):
            resolve_sqlite_db_path()

    def test_default_url_resolves_to_default_path(self, monkeypatch):
        monkeypatch.delenv("CQ_DATABASE_URL", raising=False)
        monkeypatch.delenv("CQ_DB_PATH", raising=False)

        url, path = resolve_sqlite_db_path()

        assert url == "sqlite:////data/cq.db"
        assert path == Path("/data/cq.db")
