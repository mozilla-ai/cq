"""Duration-string parser for API key TTLs.

The grammar matches the cq SDK's ``cq.ttl`` parser: a single positive
ASCII integer followed by exactly one unit suffix from ``s``, ``m``,
``h``, ``d``. Zero is rejected because a zero-TTL key is meaningless.
Parsing is case-insensitive on input and always returns the canonical
lower-case form so the value the platform persists is unambiguous
regardless of which client emitted it.

This module mirrors the SDK parser locally so the platform can validate
without taking a runtime dependency on a specific SDK release. The two
implementations must agree on grammar, max bound, and case-folding;
their tests should be kept in lockstep.

TODO(#359): drop this module once cq-sdk publishes ``cq.ttl``. The
server pins cq-sdk from PyPI, so switching to ``from cq.ttl import
parse_ttl`` requires a published SDK release bump in
``server/backend/pyproject.toml``.
"""

import re
from datetime import timedelta

# MAX_TTL is the upper bound the platform accepts for an API-key TTL.
# Exposed so callers can quote it in --help text or error messages
# without the value drifting from the validator.
MAX_TTL = timedelta(days=365)

# _CANONICAL_MAX is the canonical (lower-case, on-wire) rendering of
# MAX_TTL. Embedded in error messages so the wording matches the
# grammar the platform persists.
_CANONICAL_MAX = "365d"

# _MAX_CANONICAL_LEN caps the canonical input length so a caller cannot
# make ``int()`` do CPU work proportional to a multi-megabyte digit run.
# The longest legitimate value is ``"31536000s"`` (9 chars); the bound
# here is generous enough to tolerate leading zeros and tight enough to
# reject obvious abuse. The platform's HTTP layer already caps body
# size, but the parser self-defends so this module is safe to call from
# any context.
_MAX_CANONICAL_LEN = 16

# _MAX_SECONDS is MAX_TTL converted to seconds, cached here so the
# arithmetic check in ``parse_ttl`` does not recompute on every call.
_MAX_SECONDS = int(MAX_TTL.total_seconds())

# _MAX_ECHO_LEN caps the number of characters of the original input
# echoed in any error message. Bounds the size of the exception string
# so an attacker-controlled megabyte input does not produce a megabyte
# error (which would amplify allocation cost and bloat logs). Mirrors
# the truncation budget in sdk/python/cq.ttl and sdk/go/ttl.
_MAX_ECHO_LEN = 64

# _PATTERN matches the canonical (lower-case, trimmed) grammar:
# one or more ASCII digits followed by exactly one unit suffix.
# [0-9]+ rather than \d+: Python's \d would accept Unicode "decimal
# digit" characters (category Nd), so values like "١٢h" would otherwise
# parse and diverge from sdk/go/ttl which uses an explicit ASCII class.
_PATTERN = re.compile(r"^([0-9]+)([smhd])$")

# _UNIT_SECONDS maps each accepted unit suffix to its duration in
# seconds. Lookup is keyed by the unit byte the regexp captured, so
# every key in this map must appear in _PATTERN's character class.
_UNIT_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
}


def parse_ttl(value: str) -> tuple[str, timedelta]:
    r"""Parse a TTL duration string.

    Args:
        value: A string matching ``^[0-9]+[smhd]$`` after case-folding
            and whitespace trimming. Both ``"30D"`` and ``"30d"`` are
            accepted and return the lower-case canonical form ``"30d"``.

    Returns:
        A ``(canonical, duration)`` tuple. ``canonical`` is the
        lower-case, whitespace-stripped form of ``value`` suitable for
        persistence; ``duration`` is the parsed ``timedelta``.

    Raises:
        ValueError: If the string is empty, malformed, zero, or exceeds
            the maximum allowed TTL of 365 days.
    """
    canonical = value.strip().lower() if value else ""
    if not canonical:
        raise ValueError("TTL is required")
    # Length-cap before int() so a multi-megabyte digit run cannot make
    # the parser do real CPU work before the MAX check fires.
    if len(canonical) > _MAX_CANONICAL_LEN:
        raise ValueError(f"TTL {_echo(value)!r} exceeds maximum of {_CANONICAL_MAX}")
    match = _PATTERN.fullmatch(canonical)
    if match is None:
        raise ValueError(f"Invalid TTL {_echo(value)!r}; expected format like '30s', '15m', '2h', or '90d'")
    quantity = int(match.group(1))
    if quantity <= 0:
        raise ValueError("TTL must be greater than zero")
    seconds = quantity * _UNIT_SECONDS[match.group(2)]
    if seconds > _MAX_SECONDS:
        raise ValueError(f"TTL {_echo(value)!r} exceeds maximum of {_CANONICAL_MAX}")
    return canonical, timedelta(seconds=seconds)


def _echo(value: str) -> str:
    """Return ``value`` truncated for safe inclusion in error messages."""
    return value if len(value) <= _MAX_ECHO_LEN else value[:_MAX_ECHO_LEN]
