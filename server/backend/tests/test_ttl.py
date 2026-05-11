"""Tests for the TTL duration parser."""

from datetime import timedelta

import pytest

from cq_server.ttl import MAX_TTL, parse_ttl


class TestParseTtlHappyPath:
    def test_seconds(self) -> None:
        assert parse_ttl("1s") == ("1s", timedelta(seconds=1))
        assert parse_ttl("30s") == ("30s", timedelta(seconds=30))

    def test_minutes(self) -> None:
        assert parse_ttl("15m") == ("15m", timedelta(minutes=15))

    def test_hours(self) -> None:
        assert parse_ttl("2h") == ("2h", timedelta(hours=2))

    def test_days(self) -> None:
        assert parse_ttl("7d") == ("7d", timedelta(days=7))

    def test_max_boundary(self) -> None:
        assert parse_ttl("365d") == ("365d", MAX_TTL)

    def test_leading_zero_is_accepted(self) -> None:
        assert parse_ttl("007d") == ("007d", timedelta(days=7))


class TestParseTtlCanonicalisation:
    """Upper-case and surrounding whitespace fold to canonical lower-case."""

    @pytest.mark.parametrize(
        ("value", "want_canonical", "want_duration"),
        [
            ("30D", "30d", timedelta(days=30)),
            ("12H", "12h", timedelta(hours=12)),
            ("45M", "45m", timedelta(minutes=45)),
            ("60S", "60s", timedelta(seconds=60)),
            ("  90d  ", "90d", timedelta(days=90)),
            ("\t30d\n", "30d", timedelta(days=30)),
        ],
    )
    def test_normalises(self, value: str, want_canonical: str, want_duration: timedelta) -> None:
        canonical, duration = parse_ttl(value)
        assert canonical == want_canonical
        assert duration == want_duration


class TestParseTtlRejections:
    @pytest.mark.parametrize(
        "value",
        [
            "",
            " ",
            "0s",
            "0d",
            "000h",
            "-1d",
            "1.5h",
            "1",
            "h",
            "d30",
            "1w",
            "3mo",
            "5y",
            "1h30m",
            " 1 d",
            "1 d",
            "d",
        ],
    )
    def test_rejects(self, value: str) -> None:
        with pytest.raises(ValueError):
            parse_ttl(value)

    def test_rejects_over_max(self) -> None:
        with pytest.raises(ValueError):
            parse_ttl("366d")

    def test_rejects_over_max_in_hours(self) -> None:
        with pytest.raises(ValueError):
            parse_ttl("8761h")

    def test_rejects_over_max_in_minutes(self) -> None:
        with pytest.raises(ValueError):
            parse_ttl("525601m")

    def test_rejects_over_max_in_seconds(self) -> None:
        with pytest.raises(ValueError):
            parse_ttl("31536001s")

    def test_rejects_absurdly_large_quantity(self) -> None:
        with pytest.raises(ValueError):
            parse_ttl("999999999999999999999d")

    def test_rejects_megabyte_digit_run_before_int_parse(self) -> None:
        with pytest.raises(ValueError):
            parse_ttl(("9" * (1 << 20)) + "d")

    @pytest.mark.parametrize("value", ["١٢h", "١d", "1٢h"])
    def test_rejects_unicode_digits(self, value: str) -> None:
        with pytest.raises(ValueError):
            parse_ttl(value)


class TestParseTtlErrorMessageBounds:
    def test_megabyte_input_produces_bounded_error(self) -> None:
        huge = ("9" * (1 << 20)) + "d"
        with pytest.raises(ValueError) as exc:
            parse_ttl(huge)
        assert len(str(exc.value)) < 256
