"""FastAPI dependencies shared across routers."""

import os
from datetime import UTC, datetime

from fastapi import BackgroundTasks, Depends, HTTPException, Request

from .api_keys import PREFIX, hash_token
from .store import RemoteStore

AUTH_DISABLED_ENV = "CQ_DISABLE_API_KEY_AUTH"
API_KEY_PEPPER_ENV = "CQ_API_KEY_PEPPER"  # pragma: allowlist secret
ANONYMOUS_USERNAME = "anonymous"


def get_store(request: Request) -> RemoteStore:
    """FastAPI dependency that returns the store from app state.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The RemoteStore instance attached to the application state.
    """
    return request.app.state.store


def is_api_key_auth_disabled() -> bool:
    """Return True when API key enforcement has been opted out for the process.

    Controlled by the ``CQ_DISABLE_API_KEY_AUTH`` environment variable; any
    value other than ``"1"`` leaves enforcement enabled.
    """
    return os.environ.get(AUTH_DISABLED_ENV) == "1"


def get_api_key_pepper(request: Request) -> str:
    """Return the API key pepper from application state.

    Raises:
        HTTPException: 500 if the pepper has not been configured; this
            indicates the opt-out flag was removed without the operator
            supplying ``CQ_API_KEY_PEPPER``.
    """
    pepper = getattr(request.app.state, "api_key_pepper", None)
    if not pepper:
        raise HTTPException(status_code=500, detail="Server is misconfigured")
    return pepper


def require_api_key(
    request: Request,
    background_tasks: BackgroundTasks,
    store: RemoteStore = Depends(get_store),
) -> str:
    """Authenticate an API key and return the owning user's username.

    When the opt-out flag is set, the dependency short-circuits and returns
    ``ANONYMOUS_USERNAME``. Otherwise, the ``Authorization: Bearer <token>``
    header must carry a valid, unrevoked, unexpired key.

    Args:
        request: The incoming FastAPI request.
        background_tasks: FastAPI background tasks used to record usage.
        store: The remote store.

    Returns:
        The username of the authenticated caller, or ``ANONYMOUS_USERNAME``
        when enforcement is disabled.

    Raises:
        HTTPException: 401 on any authentication failure.
    """
    if is_api_key_auth_disabled():
        return ANONYMOUS_USERNAME
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid API key")
    token = header.removeprefix("Bearer ")
    if not token.startswith(PREFIX):
        raise HTTPException(status_code=401, detail="Invalid API key")
    pepper = get_api_key_pepper(request)
    row = store.get_api_key_by_hash(hash_token(token, pepper=pepper))
    if row is None or row["revoked_at"] is not None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if datetime.fromisoformat(row["expires_at"]) <= datetime.now(UTC):
        raise HTTPException(status_code=401, detail="Invalid API key")
    background_tasks.add_task(store.touch_api_key_last_used, row["id"])
    return row["username"]
