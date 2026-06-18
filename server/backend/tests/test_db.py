"""Tests for ``cq_server.core.db.Database`` URL dispatch."""

import pytest

from cq_server.core.config import Settings
from cq_server.core.db import Database


def _settings_with_url(monkeypatch: pytest.MonkeyPatch, url: str) -> Settings:
    """Build a ``Settings`` pinned to a specific database URL."""
    monkeypatch.setenv("CQ_JWT_SECRET", "test-secret")
    monkeypatch.setenv("CQ_API_KEY_PEPPER", "test-pepper")
    monkeypatch.setenv("CQ_DATABASE_URL", url)
    return Settings()  # type: ignore[call-arg]


class TestPostgresUrlDispatch:
    """URL dispatch for PostgreSQL drivers in ``Database.__init__``."""

    def test_psycopg_url_raises_not_implemented_with_guidance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = _settings_with_url(monkeypatch, "postgresql+psycopg://u:p@h/d")
        with pytest.raises(NotImplementedError) as exc:
            Database(settings)
        message = str(exc.value)
        assert "#312" in message
        # #311 is closing with this change; the message should only
        # reference the implementation issue.
        assert "#311" not in message

    @pytest.mark.parametrize(
        "url",
        [
            "postgresql://u:p@h/d",
            "postgresql+psycopg2://u:p@h/d",
            "postgresql+asyncpg://u:p@h/d",
        ],
    )
    def test_non_canonical_postgres_raises_not_implemented_with_driver_guidance(
        self, monkeypatch: pytest.MonkeyPatch, url: str
    ) -> None:
        settings = _settings_with_url(monkeypatch, url)
        with pytest.raises(NotImplementedError) as exc:
            Database(settings)
        message = str(exc.value)
        assert "#312" in message
        # The message must steer to the canonical driver, not just echo
        # the URL.  "use postgresql+psycopg://" is unique to the
        # non-canonical branch — it won't match a psycopg2 URL repr.
        assert "use postgresql+psycopg://" in message

    def test_unsupported_scheme_raises_value_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = _settings_with_url(monkeypatch, "mysql://u:p@h/d")
        with pytest.raises(ValueError, match="Unsupported database URL scheme"):
            Database(settings)
