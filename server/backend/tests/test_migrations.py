"""Tests for Alembic baseline migration + stamp-on-startup logic.

Covers the three startup cases the migration runner has to handle:

1. ``test_fresh_database_runs_baseline_migration`` — empty file, no
   tables. Migration creates everything and stamps at baseline.
2. ``test_existing_pre_alembic_database_is_stamped`` — production-shape
   DB built by the legacy ``_ensure_schema()`` path, with seed data in
   every table. Migration runner must stamp at baseline (not re-run
   the DDL) and preserve every row.
3. ``test_already_stamped_database_is_idempotent`` — DB with
   ``alembic_version`` already at head. Re-running is a no-op.

Plus a fourth structural test:

4. ``test_baseline_schema_matches_legacy_ensure_schema`` — the in-repo
   substitute for "byte-checked against current production schema".
   Builds DB-A via legacy ``_ensure_schema`` and DB-B via the baseline
   migration and asserts they produce the equivalent set of
   tables/columns/indexes/foreign-keys. **Delete this test in #310**
   when ``_ensure_schema`` is removed and the migration becomes the
   sole source of truth.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from cq_server.migrations import BASELINE_REVISION, run_migrations
from cq_server.store import SqliteStore

# --- Helpers --------------------------------------------------------------


def _sqlite_url(db: Path) -> str:
    return f"sqlite:///{db}"


def _open_ro(db: Path) -> sqlite3.Connection:
    """Open a connection with foreign keys on, matching production PRAGMAs."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _user_table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'").fetchall()
    return {row[0] for row in rows}


def _alembic_version(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    return None if row is None else row[0]


def _columns(conn: sqlite3.Connection, table: str) -> list[tuple[Any, ...]]:
    """Return PRAGMA table_info rows ordered by cid (= source order).

    Tuple shape: (name, type, notnull, dflt_value, pk). cid is dropped
    so the comparison is on the column list itself, not on ordering
    metadata.
    """
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [(row[1], row[2], row[3], row[4], row[5]) for row in rows]


def _explicit_indexes(conn: sqlite3.Connection, table: str) -> dict[str, dict[str, Any]]:
    """Return only `CREATE INDEX` indexes (origin = 'c').

    Implicit `sqlite_autoindex_*` indexes that SQLite generates for
    PRIMARY KEY / UNIQUE constraints are excluded — those are already
    accounted for in the column list.
    """
    out: dict[str, dict[str, Any]] = {}
    for row in conn.execute(f"PRAGMA index_list({table})").fetchall():
        # row: (seq, name, unique, origin, partial)
        name, unique, origin = row[1], bool(row[2]), row[3]
        if origin != "c":
            continue
        cols = [info[2] for info in conn.execute(f"PRAGMA index_info({name})").fetchall()]
        out[name] = {"unique": unique, "columns": cols}
    return out


def _foreign_keys(conn: sqlite3.Connection, table: str) -> list[tuple[Any, ...]]:
    """Return foreign keys ordered by (id, seq) for deterministic compare."""
    rows = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    # row: (id, seq, table, from, to, on_update, on_delete, match)
    sortable = sorted(rows, key=lambda r: (r[0], r[1]))
    return [(r[2], r[3], r[4], r[5], r[6], r[7]) for r in sortable]


def _normalized_table_shape(conn: sqlite3.Connection, table: str) -> dict[str, Any]:
    """Build a deterministic, comparable shape descriptor for one table."""
    columns = _columns(conn, table)
    # SQLite reports notnull differently on PRIMARY KEY columns
    # depending on whether the source SQL spelled NOT NULL out:
    # the legacy schema uses bare ``id TEXT PRIMARY KEY`` /
    # ``id INTEGER PRIMARY KEY AUTOINCREMENT`` (notnull=0), while
    # SQLAlchemy / Alembic always emit NOT NULL on PK columns
    # (notnull=1). Functionally equivalent for this application —
    # the code never inserts NULL into a primary key — so normalize
    # notnull on PK columns regardless of type.
    normalized_cols = []
    for name, type_, notnull, default, pk in columns:
        if pk:
            notnull = 0
        normalized_cols.append((name, type_, notnull, default, pk))
    return {
        "columns": normalized_cols,
        "indexes": _explicit_indexes(conn, table),
        "foreign_keys": _foreign_keys(conn, table),
    }


def _normalized_schema(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Whole-DB shape descriptor, keyed by user table name."""
    tables = _user_table_names(conn) - {"alembic_version"}
    return {t: _normalized_table_shape(conn, t) for t in sorted(tables)}


def _row_counts(conn: sqlite3.Connection, tables: set[str]) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


async def _seed_kus(store: SqliteStore) -> list[str]:
    """Insert three KUs covering different review states and tiers."""
    from cq.models import Context, Insight, Tier, create_knowledge_unit

    units = [
        create_knowledge_unit(
            domains=["api"],
            insight=Insight(summary="A", detail="A.", action="A!"),
            context=Context(),
            tier=Tier.PRIVATE,
            created_by="alice",
        ),
        create_knowledge_unit(
            domains=["databases"],
            insight=Insight(summary="B", detail="B.", action="B!"),
            context=Context(languages=["python"]),
            tier=Tier.PRIVATE,
            created_by="alice",
        ),
        create_knowledge_unit(
            domains=["security", "api"],
            insight=Insight(summary="C", detail="C.", action="C!"),
            context=Context(),
            tier=Tier.PRIVATE,
            created_by="alice",
        ),
    ]
    for u in units:
        await store.insert(u)
    # Approve one so reviewed_by/reviewed_at are exercised on a real row.
    await store.set_review_status(units[0].id, "approved", "reviewer-bob")
    return [u.id for u in units]


async def _seed_user_and_api_key(store: SqliteStore) -> tuple[int, str]:
    """Insert one user + one API key. Returns (user_id, key_id)."""
    await store.create_user("alice", "$2b$12$fakehashfakehashfakehashfakehashfake")
    user = await store.get_user("alice")
    assert user is not None
    user_id = int(user["id"])
    key_id = uuid.uuid4().hex
    await store.create_api_key(
        key_id=key_id,
        user_id=user_id,
        name="seed",
        labels=["test"],
        key_prefix="cqaprefi",
        key_hash="hash-" + key_id,
        ttl="30d",
        expires_at="2099-01-01T00:00:00+00:00",
    )
    return user_id, key_id


# --- Test 1: fresh database ------------------------------------------------


class TestFreshDatabase:
    def test_fresh_database_runs_baseline_migration(self, tmp_path: Path) -> None:
        db = tmp_path / "fresh.db"
        assert not db.exists()

        run_migrations(_sqlite_url(db))

        assert db.exists()
        with _open_ro(db) as conn:
            tables = _user_table_names(conn)
            assert {
                "knowledge_units",
                "knowledge_unit_domains",
                "users",
                "api_keys",
                "alembic_version",
            } <= tables
            assert _alembic_version(conn) == BASELINE_REVISION

            # knowledge_units columns and order match the historical
            # _SCHEMA_SQL + ALTER end-state on prod.
            ku_cols = [c[0] for c in _columns(conn, "knowledge_units")]
            assert ku_cols == [
                "id",
                "data",
                "status",
                "reviewed_by",
                "reviewed_at",
                "created_at",
                "tier",
            ]

            # Defaults on the columns that have them.
            ku_by_name = {c[0]: c for c in _columns(conn, "knowledge_units")}
            assert ku_by_name["status"][3] == "'pending'"
            assert ku_by_name["tier"][3] == "'private'"

            # Explicit indexes.
            ku_domain_idx = _explicit_indexes(conn, "knowledge_unit_domains")
            assert "idx_domains_domain" in ku_domain_idx
            assert ku_domain_idx["idx_domains_domain"]["columns"] == ["domain"]
            api_key_idx = _explicit_indexes(conn, "api_keys")
            assert "idx_api_keys_user" in api_key_idx
            assert api_key_idx["idx_api_keys_user"]["columns"] == ["user_id"]

            # Foreign keys with cascade.
            fks = _foreign_keys(conn, "knowledge_unit_domains")
            assert any(fk[0] == "knowledge_units" and fk[1] == "unit_id" and fk[4] == "CASCADE" for fk in fks)
            api_fks = _foreign_keys(conn, "api_keys")
            assert any(fk[0] == "users" and fk[1] == "user_id" and fk[4] == "CASCADE" for fk in api_fks)


# --- Test 2: existing pre-Alembic database with data -----------------------


class TestExistingPreAlembicDatabase:
    """The critical case: real prod DB has data, no alembic_version."""

    @pytest_asyncio.fixture()
    async def seeded_pre_alembic_db(self, tmp_path: Path) -> tuple[Path, Mapping[str, Any]]:
        """Build a production-shape SQLite DB by going through the legacy
        ``_ensure_schema()`` path, then seed every table and snapshot
        the resulting state. Returns (db_path, snapshot)."""
        db = tmp_path / "prod.db"
        store = SqliteStore(db_path=db)
        ku_ids = await _seed_kus(store)
        user_id, key_id = await _seed_user_and_api_key(store)
        await store.close()

        with _open_ro(db) as conn:
            assert "alembic_version" not in _user_table_names(conn)
            data_tables = _user_table_names(conn)
            snapshot = {
                "schema": _normalized_schema(conn),
                "counts": _row_counts(conn, data_tables),
                "kus": conn.execute(
                    "SELECT id, data, status, reviewed_by, reviewed_at, created_at, tier "
                    "FROM knowledge_units ORDER BY id"
                ).fetchall(),
                "ku_ids": sorted(ku_ids),
                "user_id": user_id,
                "key_id": key_id,
            }
        return db, snapshot

    async def test_existing_pre_alembic_database_is_stamped(
        self, seeded_pre_alembic_db: tuple[Path, Mapping[str, Any]]
    ) -> None:
        db, before = seeded_pre_alembic_db

        run_migrations(_sqlite_url(db))

        with _open_ro(db) as conn:
            # Stamp landed at baseline — proves we did NOT re-run the DDL,
            # otherwise Alembic would have errored on CREATE TABLE
            # against an existing table.
            assert _alembic_version(conn) == BASELINE_REVISION

            # Schema for user tables is structurally unchanged.
            assert _normalized_schema(conn) == before["schema"]

            # Every row preserved.
            data_tables = _user_table_names(conn) - {"alembic_version"}
            assert _row_counts(conn, data_tables) == before["counts"]

            # KU rows still exactly equal (every column).
            assert (
                conn.execute(
                    "SELECT id, data, status, reviewed_by, reviewed_at, created_at, tier "
                    "FROM knowledge_units ORDER BY id"
                ).fetchall()
                == before["kus"]
            )

    async def test_pre_alembic_migration_is_idempotent(
        self, seeded_pre_alembic_db: tuple[Path, Mapping[str, Any]]
    ) -> None:
        """SIGTERM-during-stamp could land us here; re-running must not
        corrupt anything."""
        db, before = seeded_pre_alembic_db

        run_migrations(_sqlite_url(db))
        # Run a second time on the now-stamped DB.
        run_migrations(_sqlite_url(db))

        with _open_ro(db) as conn:
            assert _alembic_version(conn) == BASELINE_REVISION
            assert _normalized_schema(conn) == before["schema"]
            data_tables = _user_table_names(conn) - {"alembic_version"}
            assert _row_counts(conn, data_tables) == before["counts"]


# --- Test 3: already-stamped database --------------------------------------


class TestAlreadyStampedDatabase:
    async def test_already_stamped_database_is_idempotent(self, tmp_path: Path) -> None:
        db = tmp_path / "stamped.db"

        # First call: fresh DB → upgrade head.
        run_migrations(_sqlite_url(db))

        # Insert a sentinel row through a real SqliteStore.
        store = SqliteStore(db_path=db)
        try:
            ku_ids = await _seed_kus(store)
        finally:
            await store.close()

        with _open_ro(db) as conn:
            counts_before = _row_counts(conn, _user_table_names(conn) - {"alembic_version"})
            schema_before = _normalized_schema(conn)

        # Second call on the same DB: must be a no-op.
        run_migrations(_sqlite_url(db))

        with _open_ro(db) as conn:
            assert _alembic_version(conn) == BASELINE_REVISION
            data_tables = _user_table_names(conn) - {"alembic_version"}
            assert _row_counts(conn, data_tables) == counts_before
            assert _normalized_schema(conn) == schema_before
            # Sentinel rows survived.
            ku_rows = conn.execute("SELECT id FROM knowledge_units ORDER BY id").fetchall()
            assert sorted(r[0] for r in ku_rows) == sorted(ku_ids)


# --- Test 4: parity with legacy _ensure_schema -----------------------------


class TestBaselineMatchesLegacySchema:
    """In-repo proxy for #305's "byte-checked against production schema".

    The current ``_ensure_schema()`` is what builds every production DB,
    so if the baseline migration produces a structurally equivalent
    schema on an empty file, we have parity with prod.

    Caveat: ``_normalized_table_shape`` deliberately normalises NOT-NULL
    on PRIMARY KEY columns to ``0`` because the legacy schema and
    SQLAlchemy/Alembic disagree on whether to spell ``NOT NULL`` out for
    PKs. This is load-bearing — the parity check accepts any future
    PK-nullability divergence as well, including bugs introduced by a
    new migration. Future migrations that touch PK columns should be
    reviewed against the migration source, not just this test.

    DELETE THIS TEST in #310 alongside ``_ensure_schema()`` — once
    the legacy path is gone there is nothing to compare against and
    the migration is the sole source of truth.
    """

    async def test_baseline_schema_matches_legacy_ensure_schema(self, tmp_path: Path) -> None:
        legacy_db = tmp_path / "legacy.db"
        migrated_db = tmp_path / "migrated.db"

        # DB-A: legacy code path.
        await SqliteStore(db_path=legacy_db).close()
        # DB-B: baseline migration.
        run_migrations(_sqlite_url(migrated_db))

        with _open_ro(legacy_db) as conn_a, _open_ro(migrated_db) as conn_b:
            schema_a = _normalized_schema(conn_a)
            schema_b = _normalized_schema(conn_b)

        # alembic_version is excluded by _normalized_schema; everything
        # else must agree.
        assert schema_b == schema_a, (
            "Baseline migration drifted from current production schema — "
            "fix the migration so PRAGMA table_info / PRAGMA index_list / "
            "PRAGMA foreign_key_list match what _ensure_schema() produces."
        )


# --- Test 5: default URL resolution ----------------------------------------


class TestSqliteParentDirCreation:
    """Regression: relative ``sqlite:///./data/x.db`` URLs must create
    ``./data`` (relative to cwd), not an absolute ``/data`` directory.

    The earlier ``urlparse(url).path`` implementation produced
    ``/./data/x.db`` for that URL, whose ``Path.parent`` is the absolute
    ``/data`` — so ``mkdir`` either failed with PermissionError outside
    of Docker or silently created the wrong directory inside it.
    """

    def test_relative_sqlite_url_creates_relative_parent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        rel_db = "subdir/nested.db"
        url = f"sqlite:///{rel_db}"
        assert not (tmp_path / "subdir").exists()

        run_migrations(url)

        # Parent directory was created relative to cwd, not at filesystem root.
        assert (tmp_path / "subdir").is_dir()
        assert (tmp_path / rel_db).exists()
        # Filesystem root must not have been touched.
        assert not Path("/subdir").exists()


class TestPercentInUrlIsConfigParserSafe:
    """Regression: literal ``%`` in the database URL must not crash startup.

    The original implementation called ``cfg.set_main_option(
    "sqlalchemy.url", url)``, which routes through ConfigParser's
    interpolation engine and raises ``ValueError: invalid interpolation
    syntax`` eagerly on any ``%``. Both call sites (``run_migrations``
    and ``alembic/env.py``) were affected. The fix bypasses the ini
    option entirely — the runtime hands a connection in via
    ``cfg.attributes["connection"]`` and the CLI path builds its own
    engine from a URL resolved at use-time.

    A ``%`` in a SQLite filename exercises the same code path that a
    ``%``-encoded Postgres password (e.g. ``p%40ss``) would hit, so we
    can pin the regression without a real database server.
    """

    @pytest.mark.parametrize(
        "filename",
        [
            "100%real.db",
            "p%40ss.db",
            "weird%%name.db",
        ],
    )
    def test_runtime_path_handles_percent_in_url(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename: str
    ) -> None:
        monkeypatch.chdir(tmp_path)
        url = f"sqlite:///{filename}"

        run_migrations(url)

        db = tmp_path / filename
        assert db.exists()
        with _open_ro(db) as conn:
            assert _alembic_version(conn) == BASELINE_REVISION

    def test_cli_path_handles_percent_in_url(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Drives the CLI branch in ``env.py`` — no connection on the Config.

        Without the fix, ``env.py``'s module-level ``set_main_option(
        "sqlalchemy.url", resolve_database_url())`` would crash on import
        before any migration ran.
        """
        from alembic import command
        from alembic.config import Config

        from cq_server.migrations import _ALEMBIC_INI

        monkeypatch.chdir(tmp_path)
        db = tmp_path / "100%real.db"
        monkeypatch.setenv("CQ_DATABASE_URL", f"sqlite:///{db}")
        monkeypatch.delenv("CQ_DB_PATH", raising=False)

        cfg = Config(str(_ALEMBIC_INI))
        # Deliberately do not set ``cfg.attributes["connection"]`` —
        # this is the path ``alembic upgrade head`` from the shell takes.
        command.upgrade(cfg, "head")

        assert db.exists()
        with _open_ro(db) as conn:
            assert _alembic_version(conn) == BASELINE_REVISION


class TestDefaultDatabaseUrlResolution:
    """``run_migrations()`` with no arg must honour ``resolve_database_url``.

    The startup path in ``app.py`` calls ``run_migrations()`` with no
    argument so that ``CQ_DATABASE_URL`` (and the ``CQ_DB_PATH``
    fallback) take effect. Cover both env-var branches.
    """

    def test_run_migrations_uses_cq_db_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        db = tmp_path / "from_env.db"
        monkeypatch.delenv("CQ_DATABASE_URL", raising=False)
        monkeypatch.setenv("CQ_DB_PATH", str(db))

        run_migrations()

        assert db.exists()
        with _open_ro(db) as conn:
            assert _alembic_version(conn) == BASELINE_REVISION

    def test_cq_database_url_takes_precedence_over_cq_db_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        winning = tmp_path / "winning.db"
        losing = tmp_path / "losing.db"
        monkeypatch.setenv("CQ_DATABASE_URL", _sqlite_url(winning))
        monkeypatch.setenv("CQ_DB_PATH", str(losing))

        run_migrations()

        assert winning.exists()
        assert not losing.exists()
