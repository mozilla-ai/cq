"""Authentication primitives: password hashing and JWT creation/validation.

Higher layers consume these helpers:

- ``hash_password`` / ``verify_password`` are used by the login route and
  by tests that seed users.
- ``create_token`` issues a JWT after a successful login.
- ``verify_token`` is consumed by the ``get_current_user`` FastAPI
  dependency in ``api/deps.py``.
- ``jwt_secret`` reads the configured signing secret from the environment.

Route handlers and FastAPI dependencies live elsewhere; this module is
pure utility and has no FastAPI surface.
"""

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt


def create_token(username: str, *, secret: str, ttl_hours: int = 24) -> str:
    """Create a JWT token for the given username."""
    now = datetime.now(UTC)
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + timedelta(hours=ttl_hours),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def jwt_secret() -> str:
    """Return the JWT signing secret, failing if unset.

    Returns:
        The value of the CQ_JWT_SECRET environment variable.

    Raises:
        RuntimeError: If the environment variable is not set.
    """
    secret = os.environ.get("CQ_JWT_SECRET")
    if not secret:
        raise RuntimeError("CQ_JWT_SECRET environment variable is required")
    return secret


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode(), hashed.encode())


def verify_token(token: str, *, secret: str) -> dict[str, Any]:
    """Verify and decode a JWT token."""
    return jwt.decode(token, secret, algorithms=["HS256"])
