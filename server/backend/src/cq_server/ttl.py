"""Duration-string parser for API key TTLs.

Accepts a duration string of the form used by Go's ``time.ParseDuration``
and by Prometheus range durations: ``30s``, ``15m``, ``2h``, ``90d``. The
grammar is a strict subset of those: exactly one integer quantity followed
by a single unit suffix from ``s``, ``m``, ``h``, ``d``. Longer units such
as ``mo`` and ``y`` are deliberately not supported to keep the grammar
unambiguous.
"""

import re
from datetime import timedelta

_PATTERN = re.compile(r"^(\d+)([smhd])$")

_UNIT_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
}

MAX_TTL = timedelta(days=365)
_MAX_SECONDS = int(MAX_TTL.total_seconds())


def parse_ttl(value: str) -> timedelta:
    r"""Parse a TTL duration string into a ``timedelta``.

    Args:
        value: A string matching ``^\d+[smhd]$``.

    Returns:
        The parsed duration.

    Raises:
        ValueError: If the string is empty, malformed, zero, or exceeds the
            maximum allowed TTL of 365 days.
    """
    match = _PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"Invalid TTL '{value}'; expected format like '30s', '15m', '2h', or '90d'")
    quantity = int(match.group(1))
    if quantity <= 0:
        raise ValueError("TTL must be greater than zero")
    seconds = quantity * _UNIT_SECONDS[match.group(2)]
    if seconds > _MAX_SECONDS:
        raise ValueError(f"TTL '{value}' exceeds maximum of 365d")
    duration = timedelta(seconds=seconds)
    return duration
