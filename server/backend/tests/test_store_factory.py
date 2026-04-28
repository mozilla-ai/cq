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
    def test_postgres_psycopg_url_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError) as exc:
            create_store("postgresql+psycopg://u:p@h/d")
        # The message must point at the Phase 2 children so users hit a
        # self-explanatory error rather than a "did I typo my URL?" loop.
        assert "#311" in str(exc.value) or "#312" in str(exc.value)

    def test_bare_postgresql_url_also_raises_not_implemented(self) -> None:
        # Bare ``postgresql://`` (no driver) is a common copy-paste from
        # libpq URLs; rejecting it with the same NotImplementedError
        # avoids dropping the user into a SQLAlchemy dialect-load failure.
        with pytest.raises(NotImplementedError):
            create_store("postgresql://u:p@h/d")


class TestUnknownScheme:
    def test_unknown_scheme_rejected(self) -> None:
        with pytest.raises(ValueError, match="mysql"):
            create_store("mysql://u:p@h/d")
