"""Tests for the ``create_store`` URL → backend factory.

Covers the dispatch contract spelled out in #309: SQLite URLs return a
working ``SqliteStore``, Postgres URLs raise ``NotImplementedError`` with
guidance pointing at the Phase 2 child issues, and unsupported schemes
raise ``ValueError``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cq.models import Insight, create_knowledge_unit

from cq_server.store import SqliteStore, create_store


class TestSqlite:
    async def test_sqlite_url_returns_sqlite_store(self, tmp_path: Path) -> None:
        db = tmp_path / "factory.db"
        store = create_store(f"sqlite:///{db}")
        try:
            assert isinstance(store, SqliteStore)
            unit = create_knowledge_unit(
                domains=["factory"],
                insight=Insight(summary="s", detail="d", action="a"),
            )
            await store.insert(unit)
            assert await store.get_any(unit.id) is not None
            assert db.exists()
        finally:
            await store.close()

    async def test_sqlite_url_creates_parent_directory(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c.db"
        store = create_store(f"sqlite:///{nested}")
        try:
            assert nested.parent.is_dir()
        finally:
            await store.close()

    def test_blank_sqlite_database_rejected(self) -> None:
        with pytest.raises(ValueError, match="file path"):
            create_store("sqlite:///")

    def test_in_memory_sqlite_rejected(self) -> None:
        with pytest.raises(ValueError, match="in-memory"):
            create_store("sqlite:///:memory:")


class TestPostgres:
    @pytest.mark.parametrize(
        "url",
        [
            # Bare ``postgresql://`` is a common copy-paste from libpq URLs;
            # the explicit driver suffixes cover the drivers users actually
            # paste — psycopg v3 (#311's target), psycopg2 (still ubiquitous),
            # and asyncpg. All four must hit the same NotImplementedError so
            # the #311/#312 pointer is the user's first signal rather than a
            # generic "unsupported scheme" or a SQLAlchemy dialect-load
            # failure.
            "postgresql://u:p@h/d",
            "postgresql+psycopg://u:p@h/d",
            "postgresql+psycopg2://u:p@h/d",
            "postgresql+asyncpg://u:p@h/d",
        ],
    )
    def test_postgres_url_raises_not_implemented_with_guidance(self, url: str) -> None:
        with pytest.raises(NotImplementedError) as exc:
            create_store(url)
        assert "#311" in str(exc.value) or "#312" in str(exc.value)


class TestUnknownScheme:
    def test_unknown_scheme_rejected(self) -> None:
        with pytest.raises(ValueError, match="mysql"):
            create_store("mysql://u:p@h/d")


class TestMalformedUrl:
    def test_malformed_url_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid CQ_DATABASE_URL"):
            create_store("not a url")
