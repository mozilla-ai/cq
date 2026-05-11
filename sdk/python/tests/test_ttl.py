"""Tests for the cq.ttl duration parser."""

from __future__ import annotations

from datetime import timedelta

import pytest

from cq.ttl import MAX, TTLError, parse


class TestParseHappyPath:
    """Lower-case canonical inputs return the parsed duration verbatim."""

    @pytest.mark.parametrize(
        ("value", "want"),
        [
            ("1s", timedelta(seconds=1)),
            ("30s", timedelta(seconds=30)),
            ("15m", timedelta(minutes=15)),
            ("2h", timedelta(hours=2)),
            ("7d", timedelta(days=7)),
        ],
    )
    def test_lower_case(self, value: str, want: timedelta) -> None:
        canonical, duration = parse(value)
        assert canonical == value
        assert duration == want

    def test_max_boundary(self) -> None:
        canonical, duration = parse("365d")
        assert canonical == "365d"
        assert duration == MAX

    def test_leading_zero_is_accepted(self) -> None:
        canonical, duration = parse("007d")
        assert canonical == "007d"
        assert duration == timedelta(days=7)


class TestParseCanonicalisation:
    """Upper-case and whitespace inputs canonicalise to lower-case stripped."""

    @pytest.mark.parametrize(
        ("value", "want_canonical", "want_duration"),
        [
            ("3D", "3d", timedelta(days=3)),
            ("2H", "2h", timedelta(hours=2)),
            ("45M", "45m", timedelta(minutes=45)),
            ("60S", "60s", timedelta(seconds=60)),
            ("  90d  ", "90d", timedelta(days=90)),
            ("\t30d\n", "30d", timedelta(days=30)),
        ],
    )
    def test_normalises(self, value: str, want_canonical: str, want_duration: timedelta) -> None:
        canonical, duration = parse(value)
        assert canonical == want_canonical
        assert duration == want_duration


class TestParseRejections:
    """Inputs outside the grammar raise ``TTLError`` (a ``ValueError``)."""

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
        with pytest.raises(TTLError):
            parse(value)

    def test_rejects_over_max(self) -> None:
        with pytest.raises(TTLError):
            parse("366d")

    def test_rejects_over_max_in_hours(self) -> None:
        with pytest.raises(TTLError):
            parse("8761h")

    def test_rejects_over_max_in_minutes(self) -> None:
        with pytest.raises(TTLError):
            parse("525601m")

    def test_rejects_over_max_in_seconds(self) -> None:
        with pytest.raises(TTLError):
            parse("31536001s")

    def test_rejects_absurdly_large_quantity(self) -> None:
        with pytest.raises(TTLError):
            parse("999999999999999999999d")

    def test_rejects_megabyte_digit_run_before_int_parse(self) -> None:
        # Self-defends against unbounded ``int()`` work even outside an
        # HTTP layer that would normally cap body size.
        with pytest.raises(TTLError):
            parse(("9" * (1 << 20)) + "d")

    @pytest.mark.parametrize("value", ["١٢h", "١d", "1٢h"])
    def test_rejects_unicode_digits(self, value: str) -> None:
        # Python's \d would otherwise accept Nd-category characters
        # (e.g. Arabic-Indic) and diverge from sdk/go/ttl's [0-9]+.
        with pytest.raises(TTLError):
            parse(value)


class TestErrorMessageBounds:
    """Error messages echo a bounded prefix of the user input.

    An attacker-controlled megabyte input must not produce a megabyte
    exception string; the parser caps the echoed prefix the same way
    sdk/go/ttl does.
    """

    def test_megabyte_input_produces_bounded_error(self) -> None:
        huge = ("9" * (1 << 20)) + "d"
        with pytest.raises(TTLError) as exc:
            parse(huge)
        assert len(str(exc.value)) < 256


class TestExceptionContract:
    """``TTLError`` subclasses ``ValueError`` for backward compatibility."""

    def test_ttl_error_is_value_error(self) -> None:
        with pytest.raises(ValueError):
            parse("not-a-ttl")

    def test_error_message_quotes_original_input(self) -> None:
        with pytest.raises(TTLError, match="'1W'"):
            parse("1W")

    def test_error_message_quotes_over_max_input(self) -> None:
        with pytest.raises(TTLError, match="'366d'"):
            parse("366d")
