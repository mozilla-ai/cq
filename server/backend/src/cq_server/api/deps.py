"""FastAPI dependencies shared across routers."""

from __future__ import annotations

import hmac
import os

import jwt
from fastapi import BackgroundTasks, Depends, HTTPException, Request

from ..api_keys import decode_token, hash_secret
from ..auth import verify_token
from ..store import Store

API_KEY_PEPPER_ENV = "CQ_API_KEY_PEPPER"  # pragma: allowlist secret


def _get_jwt_secret() -> str:
    """Return the JWT secret, failing if unset.

    Returns:
        The value of the CQ_JWT_SECRET environment variable.

    Raises:
        RuntimeError: If the environment variable is not set.
    """
    secret = os.environ.get("CQ_JWT_SECRET")
    if not secret:
        raise RuntimeError("CQ_JWT_SECRET environment variable is required")
    return secret


def get_api_key_pepper(request: Request) -> str:
    """Return the API key pepper from application state.

    Raises:
        HTTPException: 500 if the pepper has not been configured.
    """
    pepper = getattr(request.app.state, "api_key_pepper", None)
    if not pepper:
        raise HTTPException(status_code=500, detail="Server is misconfigured")
    return pepper


def get_current_user(request: Request) -> str:
    """FastAPI dependency that extracts and validates the JWT from the Authorization header.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The username extracted from the validated token.

    Raises:
        HTTPException: With status 401 if the header is missing, malformed, or the token is invalid.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = auth_header.removeprefix("Bearer ")
    try:
        payload = verify_token(token, secret=_get_jwt_secret())
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    return payload["sub"]


def get_store(request: Request) -> Store:
    """FastAPI dependency that returns the store from app state.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The Store instance attached to the application state.
    """
    return request.app.state.store


async def require_api_key(
    request: Request,
    background_tasks: BackgroundTasks,
    store: Store = Depends(get_store),
) -> str:
    """Authenticate an API key and return the owning user's username.

    The ``Authorization: Bearer <token>`` header must carry a valid,
    unrevoked, unexpired key. The token is decoded to its key id and
    secret components; the stored hash of the secret is compared to a
    fresh HMAC of the presented secret using ``hmac.compare_digest`` to
    avoid timing side channels.

    Args:
        request: The incoming FastAPI request.
        background_tasks: FastAPI background tasks used to record usage.
        store: The store dependency.

    Returns:
        The username of the authenticated caller.

    Raises:
        HTTPException: 401 on any authentication failure.
    """
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid API key")
    token = header.removeprefix("Bearer ")
    try:
        key_id, secret = decode_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid API key") from exc
    pepper = get_api_key_pepper(request)
    row = await store.get_active_api_key_by_id(key_id.hex)
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not hmac.compare_digest(row["key_hash"], hash_secret(secret, pepper=pepper)):
        raise HTTPException(status_code=401, detail="Invalid API key")
    background_tasks.add_task(store.touch_api_key_last_used, row["id"])
    return row["username"]
