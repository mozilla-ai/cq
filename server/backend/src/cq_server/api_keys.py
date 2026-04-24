"""API key token encoding and hashing.

Tokens follow a versioned, dot-separated format so the key's database row
can be located by identifier rather than by hashing the entire plaintext.
This lets the server store only a hash of the random secret component and
compare it to the presented secret in constant time.

Format: ``{NAMESPACE}.{VERSION}.{key_id_hex}.{secret}``

Hashing uses HMAC-SHA256 with a server-side pepper over the secret only.
"""

import base64
import hmac
import secrets
import uuid
from hashlib import sha256

TOKEN_NAMESPACE = "cqa"
TOKEN_VERSION = "v1"

_SECRET_BYTES = 32
_SECRET_PREFIX_LENGTH = 8
_TOKEN_PART_COUNT = 4


def generate_secret() -> str:
    """Return a fresh random secret string for use as an API key secret.

    The secret is 52 lowercase base32 characters encoding 32 random bytes
    (256 bits of entropy). It is the secret component of the full token
    and is never stored in plaintext.
    """
    raw = secrets.token_bytes(_SECRET_BYTES)
    return base64.b32encode(raw).decode("ascii").rstrip("=").lower()


def encode_token(*, key_id: uuid.UUID, secret: str) -> str:
    """Encode a key id and secret into the public token string.

    Args:
        key_id: The API key's identifier.
        secret: The random secret component produced by ``generate_secret``.

    Returns:
        A dot-separated token of the form ``cqa.v1.<hex>.<secret>``.
    """
    return f"{TOKEN_NAMESPACE}.{TOKEN_VERSION}.{key_id.hex}.{secret}"


def decode_token(token: str) -> tuple[uuid.UUID, str]:
    """Parse a plaintext token into its key id and secret components.

    Args:
        token: The full plaintext token presented by the caller.

    Returns:
        The ``(key_id, secret)`` pair encoded in the token.

    Raises:
        ValueError: If the token does not match the expected format.
    """
    parts = token.split(".")
    if len(parts) != _TOKEN_PART_COUNT:
        raise ValueError("token format is invalid")
    namespace, version, key_id_hex, secret = parts
    if namespace != TOKEN_NAMESPACE or version != TOKEN_VERSION or not secret:
        raise ValueError("token format is invalid")
    try:
        key_id = uuid.UUID(hex=key_id_hex)
    except ValueError as exc:
        raise ValueError("token key id is not a valid UUID") from exc
    return key_id, secret


def hash_secret(secret: str, *, pepper: str) -> str:
    """Return the HMAC-SHA256 hex digest of the secret under the pepper.

    Args:
        secret: The random secret component of an API key token.
        pepper: Server-side secret used as the HMAC key.

    Returns:
        A 64-character hex string.
    """
    return hmac.new(pepper.encode("utf-8"), secret.encode("utf-8"), sha256).hexdigest()


def secret_prefix(secret: str) -> str:
    """Return the stored display prefix for a secret.

    The prefix is the first ``_SECRET_PREFIX_LENGTH`` characters of the
    secret; enough to distinguish keys in UI listings without revealing
    any material that could be used for authentication.
    """
    return secret[:_SECRET_PREFIX_LENGTH]
