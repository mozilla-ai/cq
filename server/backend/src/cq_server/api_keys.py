"""API key token generation and hashing.

Tokens are random 256-bit values encoded as lowercase base32 and prefixed
with a stable identifier (``cqa_``) so they are easy to recognise in logs
and pick up with secret-scanning rules. Hashing uses HMAC-SHA256 with a
server-side pepper.
"""

import base64
import hmac
import secrets
from hashlib import sha256

PREFIX = "cqa_"
_TOKEN_BYTES = 32
_PREFIX_DISPLAY_LENGTH = 8


def generate_plaintext() -> str:
    """Return a fresh random API key plaintext.

    The token is ``PREFIX`` followed by 52 lowercase base32 characters
    encoding 32 random bytes (256 bits of entropy).
    """
    raw = secrets.token_bytes(_TOKEN_BYTES)
    encoded = base64.b32encode(raw).decode("ascii").rstrip("=").lower()
    return f"{PREFIX}{encoded}"


def hash_token(plaintext: str, *, pepper: str) -> str:
    """Return the HMAC-SHA256 hex digest of the plaintext under the pepper.

    Args:
        plaintext: The full plaintext token, including the ``cqa_`` prefix.
        pepper: Server-side secret used as the HMAC key.

    Returns:
        A 64-character hex string.
    """
    return hmac.new(pepper.encode("utf-8"), plaintext.encode("utf-8"), sha256).hexdigest()


def token_prefix(plaintext: str) -> str:
    """Return the stored display prefix for a plaintext token.

    This is the first ``_PREFIX_DISPLAY_LENGTH`` characters — enough to
    distinguish keys in UI listings without exposing the secret.
    """
    return plaintext[:_PREFIX_DISPLAY_LENGTH]
