"""Protocol-compatibility checks for a parsed discovery document.

Both the on-disk cache and the live resolver apply the same rules so a
stale or malformed entry on disk is rejected exactly like a malformed
fresh response.
Keeping the check in one module pins that equivalence.
"""

from urllib.parse import urlparse

from ._types import SUPPORTED_API_VERSION, SUPPORTED_DISCOVERY_VERSION, NodeInfo


def validate(info: NodeInfo) -> None:
    """Reject a NodeInfo that does not describe a node this client can speak to.

    Mismatches are raised in domain terms so users see actionable messages
    rather than raw comparison failures.
    The rules:
    a supported schema version, a non-empty http(s) api_base_url with a host,
    and a supported api_version.
    """
    if info.version != SUPPORTED_DISCOVERY_VERSION:
        raise ValueError(
            f"discovery document declares version {info.version} "
            f"but this client supports {SUPPORTED_DISCOVERY_VERSION} — upgrade the client"
        )
    if not info.api_base_url:
        raise ValueError("api_base_url is required")
    parsed = urlparse(info.api_base_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"api_base_url {info.api_base_url!r} must use http or https scheme")
    if not parsed.hostname:
        raise ValueError(f"api_base_url {info.api_base_url!r} is missing a host")
    try:
        # Accessing .port forces validation of the port segment; urlparse itself is lenient
        # and would accept a non-numeric value that later fails inside the HTTP client.
        _ = parsed.port
    except ValueError as err:
        raise ValueError(f"api_base_url {info.api_base_url!r} has an invalid port") from err
    if not info.api_version:
        raise ValueError("api_version is required")
    if info.api_version != SUPPORTED_API_VERSION:
        raise ValueError(
            f"node speaks api_version {info.api_version!r} "
            f"but this client supports {SUPPORTED_API_VERSION!r} — upgrade the client"
        )
