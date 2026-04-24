"""Tests for the TTL duration parser."""

from datetime import timedelta

import pytest

from cq_server.ttl import MAX_TTL, parse_ttl


class TestParseTtlHappyPath:
    def test_seconds(self) -> None:
        assert parse_ttl("1s") == timedelta(seconds=1)
        assert parse_ttl("30s") == timedelta(seconds=30)

    def test_minutes(self) -> None:
        assert parse_ttl("15m") == timedelta(minutes=15)

    def test_hours(self) -> None:
        assert parse_ttl("2h") == timedelta(hours=2)

    def test_days(self) -> None:
        assert parse_ttl("7d") == timedelta(days=7)

    def test_max_boundary(self) -> None:
        assert parse_ttl("365d") == MAX_TTL

    def test_leading_zero_is_accepted(self) -> None:
        assert parse_ttl("007d") == timedelta(days=7)


class TestParseTtlRejections:
    @pytest.mark.parametrize(
        "value",
        [
            "",
            " ",
            "0s",
            "0d",
            "-1d",
            "1.5h",
            "1",
            "h",
            "d30",
            "30D",
            "1w",
            "3mo",
            "5y",
            "1h30m",
            " 1d",
            "1d ",
        ],
    )
    def test_rejects(self, value: str) -> None:
        with pytest.raises(ValueError):
            parse_ttl(value)

    def test_rejects_over_max(self) -> None:
        with pytest.raises(ValueError):
            parse_ttl("366d")

    def test_rejects_absurdly_large_quantity(self) -> None:
        with pytest.raises(ValueError):
            parse_ttl("999999999999999999999d")
