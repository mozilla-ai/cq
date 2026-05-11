"""Tests for ``cq_server.core.config.Settings``."""

from cq_server.core.config import Settings


def _make_settings() -> Settings:
    """Build Settings with required secrets set so optional fields can vary."""
    return Settings()  # type: ignore[call-arg]  # secrets supplied via env in each test


def test_explicit_database_url_wins(monkeypatch):
    monkeypatch.setenv("CQ_JWT_SECRET", "j")
    monkeypatch.setenv("CQ_API_KEY_PEPPER", "p")
    monkeypatch.setenv("CQ_DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setenv("CQ_DB_PATH", "/tmp/ignored.db")
    assert _make_settings().resolved_database_url == "postgresql://u:p@h/d"


def test_db_path_becomes_sqlite_url(monkeypatch, tmp_path):
    monkeypatch.setenv("CQ_JWT_SECRET", "j")
    monkeypatch.setenv("CQ_API_KEY_PEPPER", "p")
    monkeypatch.delenv("CQ_DATABASE_URL", raising=False)
    db = tmp_path / "cq.db"
    monkeypatch.setenv("CQ_DB_PATH", str(db))
    assert _make_settings().resolved_database_url == f"sqlite:///{db}"


def test_default_when_nothing_set(monkeypatch):
    monkeypatch.setenv("CQ_JWT_SECRET", "j")
    monkeypatch.setenv("CQ_API_KEY_PEPPER", "p")
    monkeypatch.delenv("CQ_DATABASE_URL", raising=False)
    monkeypatch.delenv("CQ_DB_PATH", raising=False)
    assert _make_settings().resolved_database_url == "sqlite:////data/cq.db"


def test_empty_database_url_falls_through(monkeypatch, tmp_path):
    # Container orchestrators sometimes pass empty env vars; treat the same
    # as unset so CQ_DB_PATH still wins.
    monkeypatch.setenv("CQ_JWT_SECRET", "j")
    monkeypatch.setenv("CQ_API_KEY_PEPPER", "p")
    db = tmp_path / "cq.db"
    monkeypatch.setenv("CQ_DATABASE_URL", "")
    monkeypatch.setenv("CQ_DB_PATH", str(db))
    assert _make_settings().resolved_database_url == f"sqlite:///{db}"
