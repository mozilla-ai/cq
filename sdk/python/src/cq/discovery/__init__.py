"""Node discovery for cq clients: resolve a node address into an API base URL and protocol version."""

from ._paths import default_cache_dir
from ._resolver import DiscoveryError, Resolver
from ._types import (
    DEFAULT_API_PATH,
    DEFAULT_API_VERSION,
    DEFAULT_CACHE_TTL_SECONDS,
    SUPPORTED_API_VERSION,
    SUPPORTED_DISCOVERY_VERSION,
    WELL_KNOWN_PATH,
    NodeInfo,
)

__all__ = [
    "DEFAULT_API_PATH",
    "DEFAULT_API_VERSION",
    "DEFAULT_CACHE_TTL_SECONDS",
    "DiscoveryError",
    "NodeInfo",
    "Resolver",
    "SUPPORTED_API_VERSION",
    "SUPPORTED_DISCOVERY_VERSION",
    "WELL_KNOWN_PATH",
    "default_cache_dir",
]
