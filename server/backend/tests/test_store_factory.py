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

from cq_server.store import PostgresStore, SqliteStore, create_store

from .db_helpers import init_test_db


class TestSqlite:
    async def test_sqlite_url_returns_sqlite_store(self, tmp_path: Path) -> None:
        db = tmp_path / "factory.db"
        init_test_db(db)
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
            # ``+psycopg2`` and ``+asyncpg`` cover the other drivers users
            # paste. All three must hit a clear NotImplementedError pointing
            # at the canonical ``+psycopg`` driver and Phase 2 implementation
            # (#312) rather than a generic "unsupported scheme" or a
            # SQLAlchemy dialect-load failure. The canonical ``+psycopg``
            # URL is exercised separately by
            # ``test_psycopg_url_dispatches_through_postgres_store`` since
            # it goes through the stub instead of the inline-raise branch.
            "postgresql://u:p@h/d",
            "postgresql+psycopg2://u:p@h/d",
            "postgresql+asyncpg://u:p@h/d",
        ],
    )
    def test_postgres_url_raises_not_implemented_with_guidance(self, url: str) -> None:
        with pytest.raises(NotImplementedError) as exc:
            create_store(url)
        message = str(exc.value)
        assert "#312" in message
        assert "PostgresStore" in message

    def test_psycopg_url_dispatches_through_postgres_store(self) -> None:
        # The canonical psycopg v3 URL must be routed through the
        # ``PostgresStore`` stub (not raised inline by the factory) so
        # that Phase 2 only needs to fill in the class — the factory
        # dispatch is already correct. ``Got database URL:`` is unique to
        # the stub's message; the inline-raise branch quotes the driver
        # only, so this substring proves the dispatch path was taken.
        with pytest.raises(NotImplementedError) as exc:
            create_store("postgresql+psycopg://u:p@h/d")
        message = str(exc.value)
        assert "Got database URL:" in message
        assert "#312" in message

    def test_postgres_store_stub_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError) as exc:
            PostgresStore("postgresql+psycopg://u:p@h/d")
        message = str(exc.value)
        assert "#312" in message


class TestUnknownScheme:
    def test_unknown_scheme_rejected(self) -> None:
        with pytest.raises(ValueError, match="mysql"):
            create_store("mysql://u:p@h/d")


class TestMalformedUrl:
    def test_malformed_url_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid CQ_DATABASE_URL"):
            create_store("not a url")
