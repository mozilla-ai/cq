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


class TestConfidenceSQL:
    """Verify the generated SQL stays in sync with the canonical bucket definitions."""

    def test_golden_sql(self) -> None:
        """Pin the exact query so a bucket-definition change that alters it trips here."""
        from cq.stores.postgres import _SQL_CONFIDENCE_DISTRIBUTION

        want = (
            "SELECT CASE "
            "WHEN confidence < 0.3 THEN '0.0-0.3' "
            "WHEN confidence < 0.5 THEN '0.3-0.5' "
            "WHEN confidence < 0.7 THEN '0.5-0.7' "
            "ELSE '0.7-1.0' "
            "END AS bucket, COUNT(*) AS cnt "
            "FROM (SELECT COALESCE((data->'evidence'->>'confidence')::float, 0.5) "
            "AS confidence FROM knowledge_units) sub "
            "GROUP BY bucket"
        )
        assert want == _SQL_CONFIDENCE_DISTRIBUTION

    def test_sql_tracks_canonical_buckets(self) -> None:
        """Every label gets one arm: finite bounds become WHEN, the infinite bound ELSE."""
        from cq.store import _CONFIDENCE_BUCKETS
        from cq.stores.postgres import _SQL_CONFIDENCE_DISTRIBUTION

        for threshold, label in _CONFIDENCE_BUCKETS:
            if threshold == float("inf"):
                assert f"ELSE '{label}'" in _SQL_CONFIDENCE_DISTRIBUTION
            else:
                assert f"WHEN confidence < {threshold} THEN '{label}'" in _SQL_CONFIDENCE_DISTRIBUTION

        arms = _SQL_CONFIDENCE_DISTRIBUTION.count("THEN ") + _SQL_CONFIDENCE_DISTRIBUTION.count("ELSE ")
        assert arms == len(_CONFIDENCE_BUCKETS)
