"""XDG-compliant cache directory resolution for the node discovery cache.

Computes the default on-disk location where resolved discovery documents are stored,
honoring the XDG Base Directory Specification so users can redirect the cache via XDG_CACHE_HOME.
"""

import logging
import os
from pathlib import Path

_LOGGER = logging.getLogger("cq.discovery")


def default_cache_dir() -> Path | None:
    """Return the XDG-compliant cq discovery cache directory, or None when no location is resolvable.

    Honors XDG_CACHE_HOME when set, falling back to ~/.cache/cq/discovery otherwise.
    Returns None when neither XDG_CACHE_HOME nor HOME is set;
    callers should treat None as "disable on-disk cache, use in-memory only."

    A misconfigured XDG_CACHE_HOME (set but not an absolute path) is logged at warning level
    on the `cq.discovery` logger and reported as None so the disable signal is uniform.

    NOTE: matches the Go SDK's XDG validation (whitespace trim plus absolute-path requirement);
    diverges only in surfacing the misconfiguration via a warning log instead of a returned error,
    so callers wire one consistent disable signal.
    """
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg is not None:
        trimmed = xdg.strip()
        if trimmed:
            candidate = Path(trimmed)
            if not candidate.is_absolute():
                _LOGGER.warning(
                    "discovery: XDG_CACHE_HOME must be an absolute path, got %r; disabling on-disk cache",
                    trimmed,
                )
                return None
            return candidate / "cq" / "discovery"
    home = os.environ.get("HOME")
    if not home:
        return None
    return Path(home) / ".cache" / "cq" / "discovery"
