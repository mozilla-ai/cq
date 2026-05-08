"""User-owned resources: the current user record and their API keys."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .api_keys import encode_token, generate_secret, hash_secret, secret_prefix
from .auth import get_current_user
from .deps import get_api_key_pepper, get_store
from .store import Store
from .ttl import parse_ttl

MAX_ACTIVE_API_KEYS_PER_USER = 20


class MeResponse(BaseModel):
    """Current user response body."""

    username: str
    created_at: str


class Message(BaseModel):
    """Generic message response body."""

    message: str


class CreateApiKeyRequest(BaseModel):
    """Request body for creating an API key."""

    name: str = Field(min_length=1, max_length=64)
    ttl: str = Field(min_length=1, max_length=16)
    labels: list[str] = Field(default_factory=list, max_length=16)


class ApiKeyPublic(BaseModel):
    """Public view of an API key; never includes the plaintext or hash."""

    id: str
    name: str
    labels: list[str]
    prefix: str
    ttl: str
    expires_at: str
    created_at: str
    last_used_at: str | None
    revoked_at: str | None
    is_expired: bool
    is_active: bool


class CreateApiKeyResponse(ApiKeyPublic):
    """Create response; the plaintext ``token`` is returned exactly once."""

    token: str


class ApiKeysPublic(BaseModel):
    """Collection wrapper for API key listings.

    The envelope shape leaves room for pagination metadata (e.g. a
    ``next_cursor`` field) without breaking existing clients.
    """

    data: list[ApiKeyPublic]
    count: int


def _normalise_labels(labels: list[str]) -> list[str]:
    """Trim, deduplicate, and drop empty labels while preserving order."""
    seen: dict[str, None] = {}
    for label in labels:
        cleaned = label.strip()
        if cleaned and cleaned not in seen:
            seen[cleaned] = None
    return list(seen.keys())


def _to_public(row: dict[str, Any]) -> ApiKeyPublic:
    """Build the public view of an API key row."""
    now = datetime.now(UTC)
    expires_at = datetime.fromisoformat(row["expires_at"])
    is_expired = expires_at <= now
    is_active = row["revoked_at"] is None and not is_expired
    return ApiKeyPublic(
        id=row["id"],
        name=row["name"],
        labels=list(row.get("labels") or []),
        prefix=row["key_prefix"],
        ttl=row["ttl"],
        expires_at=row["expires_at"],
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
        revoked_at=row["revoked_at"],
        is_expired=is_expired,
        is_active=is_active,
    )


async def _require_user_id(store: Store, username: str) -> int:
    """Return the integer user id for the authenticated caller.

    Raises:
        HTTPException: 404 if the user record has been removed while the JWT remains valid.
    """
    user = await store.get_user(username)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return int(user["id"])


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def me(username: str = Depends(get_current_user), store: Store = Depends(get_store)) -> MeResponse:
    """Return the current user's info.

    Args:
        username: The authenticated username from the JWT dependency.
        store: The store dependency.

    Returns:
        A MeResponse with the user's username and creation timestamp.

    Raises:
        HTTPException: With status 404 if the user no longer exists.
    """
    user = await store.get_user(username)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return MeResponse(username=user["username"], created_at=user["created_at"])


@router.post("/me/api-keys", status_code=201)
async def create_api_key_route(
    request: CreateApiKeyRequest,
    username: str = Depends(get_current_user),
    store: Store = Depends(get_store),
    pepper: str = Depends(get_api_key_pepper),
) -> CreateApiKeyResponse:
    """Create a new API key owned by the authenticated user.

    The plaintext ``token`` is returned exactly once, in this response. It
    cannot be retrieved afterwards; if the caller loses it, they must revoke
    and create a new key.

    Raises:
        HTTPException: 422 if the TTL is invalid, 409 if the user already has
            the maximum number of active keys.
    """
    try:
        duration = parse_ttl(request.ttl)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user_id = await _require_user_id(store, username)
    if await store.count_active_api_keys_for_user(user_id) >= MAX_ACTIVE_API_KEYS_PER_USER:
        raise HTTPException(
            status_code=409,
            detail=f"Maximum of {MAX_ACTIVE_API_KEYS_PER_USER} active API keys per user",
        )
    key_id = uuid.uuid4()
    secret = generate_secret()
    plaintext = encode_token(key_id=key_id, secret=secret)
    expires_at = (datetime.now(UTC) + duration).isoformat()
    row = await store.create_api_key(
        key_id=key_id.hex,
        user_id=user_id,
        name=request.name,
        labels=_normalise_labels(request.labels),
        key_prefix=secret_prefix(secret),
        key_hash=hash_secret(secret, pepper=pepper),
        ttl=request.ttl,
        expires_at=expires_at,
    )
    public = _to_public(row)
    return CreateApiKeyResponse(**public.model_dump(), token=plaintext)


@router.get("/me/api-keys")
async def list_api_keys_route(
    username: str = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> ApiKeysPublic:
    """Return the authenticated user's API keys. Never returns plaintext.

    Revoked keys are included with ``is_active: false`` so users can audit
    their own revocation history.
    """
    user_id = await _require_user_id(store, username)
    data = [_to_public(row) for row in await store.list_api_keys_for_user(user_id)]
    return ApiKeysPublic(data=data, count=len(data))


@router.post("/me/api-keys/{key_id}/revoke")
async def revoke_api_key_route(
    key_id: str,
    username: str = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> Message:
    """Revoke the given API key if it belongs to the caller.

    Revocation is a state transition; the row is retained with
    ``revoked_at`` set. Repeated revocations are idempotent and succeed.
    A 404 is returned when the key does not exist or is owned by a
    different user (uniform response, no enumeration oracle).
    """
    user_id = await _require_user_id(store, username)
    if await store.get_api_key_for_user(user_id=user_id, key_id=key_id) is None:
        raise HTTPException(status_code=404, detail="API key not found")
    await store.revoke_api_key(user_id=user_id, key_id=key_id)
    return Message(message="API key revoked.")
