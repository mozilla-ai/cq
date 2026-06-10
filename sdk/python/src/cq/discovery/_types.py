"""Type definitions and protocol constants for node discovery.

Holds the wire-level invariants shared across the discovery package:
the well-known document location, the schema and protocol versions this client understands,
the defaults applied when a node publishes no document, and the resolved view returned to callers.
"""

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

# API base path applied when a node does not publish a discovery document.
# Appended to the user-supplied address to form the effective API base URL.
DEFAULT_API_PATH: Final[str] = "/api/v1"

# Protocol version assumed when a node does not publish a discovery document.
DEFAULT_API_VERSION: Final[str] = "v1"

# URL path at which a node publishes its discovery document, relative to the user-supplied address.
WELL_KNOWN_PATH: Final[str] = "/.well-known/cq-node.json"

# Protocol version this client speaks.
# A node advertising any other version is rejected with a clear error.
SUPPORTED_API_VERSION: Final[str] = "v1"

# Discovery-document schema version this client understands.
# A document declaring any other value is rejected with a clear error
# so a future incompatible schema cannot be silently parsed with this client's assumptions.
SUPPORTED_DISCOVERY_VERSION: Final[int] = 1

# How long, in seconds, a successful discovery result is considered fresh on disk before re-probing.
DEFAULT_CACHE_TTL_SECONDS: Final[int] = 24 * 60 * 60


class NodeInfo(BaseModel):
    """Resolved view of a cq node after running discovery.

    Every field is populated either from the node's discovery document or from protocol defaults,
    so callers never see an empty api_base_url or api_version on a successful resolve.

    NOTE: callers should treat api_base_url as the complete URL to append resource paths to;
    there is no implicit version prefix to add on top.
    """

    model_config = ConfigDict(extra="forbid")

    version: int = Field(description="Discovery-document schema version.")
    api_base_url: str = Field(description="Complete URL the client uses verbatim. No implicit version prefix.")
    api_version: str = Field(description="Protocol version the node speaks.")
    node_name: str | None = Field(default=None, description="Optional human-readable display name.")
