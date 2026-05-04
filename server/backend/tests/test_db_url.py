"""Tests for resolve_database_url()."""

from cq_server.db_url import resolve_database_url


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
