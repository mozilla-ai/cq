"""Duration-string parser for the cq platform's API-key TTL field.

The grammar is a strict subset of Go's ``time.ParseDuration``: a single
positive ASCII integer followed by exactly one unit suffix from
``s``, ``m``, ``h``, ``d``. Zero is rejected because a zero-TTL key
is meaningless. Longer units such as ``mo`` and ``y`` are deliberately
not supported to keep the grammar unambiguous.

Parsing is case-insensitive on input but always returns the canonical
lower-case form so the value the platform validates and persists is
unambiguous regardless of which client emitted it.
"""

from __future__ import annotations

import re
from datetime import timedelta

__all__ = ["MAX", "TTLError", "parse"]

# Upper bound the platform accepts for an API-key TTL. Values whose
# total duration exceeds MAX are rejected. Exposed so callers can quote
# it in --help text or error messages without the string literal
# drifting between client and server.
MAX = timedelta(days=365)

_CANONICAL_MAX = "365d"

# [0-9]+ rather than \d+: Python's \d matches Unicode "decimal digit"
# (category Nd), so values like "١٢h" would otherwise parse as 12h and
# diverge from sdk/go/ttl which uses an explicit ASCII class.
_PATTERN = re.compile(r"^([0-9]+)([smhd])$")

_UNIT_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
}

_MAX_SECONDS = int(MAX.total_seconds())

# Upper bound on the canonical (post-strip, post-lower) input length.
# The longest legitimate value is "31536000s" (9 chars); the cap here is
# deliberately loose to tolerate leading zeros without forcing callers to
# strip them. Inputs longer than this are rejected before ``int()`` runs
# so the parser self-defends against unbounded-digit DoS even when used
# outside an HTTP layer that would have its own body-size limit.
_MAX_CANONICAL_LEN = 16

# Maximum number of characters of the original input echoed in any error
# message. Bounds the size of the exception string so an attacker-
# controlled megabyte input does not produce a megabyte-sized error
# (which would amplify allocation cost and bloat logs). Mirrors the
# truncation budget in sdk/go/ttl.
_MAX_ECHO_LEN = 64


def _echo(value: str) -> str:
    """Return ``value`` truncated for safe inclusion in error messages."""
    return value if len(value) <= _MAX_ECHO_LEN else value[:_MAX_ECHO_LEN]


class TTLError(ValueError):
    """Raised when a TTL value is empty, malformed, or exceeds MAX.

    Subclasses ``ValueError`` so existing call sites that catch
    ``ValueError`` (the contract the original ``cq_server.ttl`` parser
    used) continue to work.
    """


def parse(value: str) -> tuple[str, timedelta]:
    r"""Parse a TTL duration string.

    Args:
        value: A string matching ``^[0-9]+[smhd]$`` after case-folding
            and whitespace trimming.

    Returns:
        A ``(canonical, duration)`` tuple. ``canonical`` is the
        lower-case, whitespace-stripped form of ``value``; ``duration``
        is the parsed ``timedelta``. Send ``canonical`` on the wire so
        the platform stores a value independent of the input casing.

    Raises:
        TTLError: If the string is empty, malformed, zero, or exceeds
            MAX. Subclasses ``ValueError`` for backward compatibility
            with call sites that catch ``ValueError`` directly.
    """
    canonical = value.strip().lower() if value else ""
    if not canonical:
        raise TTLError("ttl is required")
    # Length-cap before int() so a multi-megabyte digit run cannot make
    # the parser do real CPU work before the MAX check fires. The bound
    # is well above any legitimate value (longest is "31536000s").
    if len(canonical) > _MAX_CANONICAL_LEN:
        raise TTLError(f"{_echo(value)!r} exceeds the maximum of {_CANONICAL_MAX}")
    match = _PATTERN.fullmatch(canonical)
    if match is None:
        raise TTLError(f"{_echo(value)!r} is not a valid duration: expected <integer><s|m|h|d>, e.g. 30d, 12h")
    quantity = int(match.group(1))
    if quantity <= 0:
        raise TTLError(f"{_echo(value)!r}: ttl must be greater than zero")
    seconds = quantity * _UNIT_SECONDS[match.group(2)]
    if seconds > _MAX_SECONDS:
        raise TTLError(f"{_echo(value)!r} exceeds the maximum of {_CANONICAL_MAX}")
    return canonical, timedelta(seconds=seconds)
