"""Unit tests for the PostgreSQL store adapter."""

import pytest

psycopg = pytest.importorskip("psycopg")


class TestPostgresStoreConstructor:
    """Validate constructor input checking without requiring a Postgres instance."""

    def test_empty_string_raises_value_error(self) -> None:
        from cq.stores.postgres import PostgresStore

        with pytest.raises(ValueError, match="connection string must not be empty"):
            PostgresStore("")

    def test_whitespace_only_raises_value_error(self) -> None:
        from cq.stores.postgres import PostgresStore

        with pytest.raises(ValueError, match="connection string must not be empty"):
            PostgresStore("   ")

    def test_unreachable_host_raises_operational_error(self) -> None:
        from cq.stores.postgres import PostgresStore

        with pytest.raises(psycopg.OperationalError):
            PostgresStore("postgres://localhost:1/nonexistent")
