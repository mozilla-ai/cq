"""Authentication: password hashing, JWT creation and validation."""

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .api_keys import generate_plaintext, hash_token, token_prefix
from .deps import get_api_key_pepper, get_store
from .store import RemoteStore
from .ttl import parse_ttl

MAX_ACTIVE_API_KEYS_PER_USER = 20


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(username: str, *, secret: str, ttl_hours: int = 24) -> str:
    """Create a JWT token for the given username."""
    now = datetime.now(UTC)
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + timedelta(hours=ttl_hours),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_token(token: str, *, secret: str) -> dict[str, Any]:
    """Verify and decode a JWT token."""
    return jwt.decode(token, secret, algorithms=["HS256"])


class LoginRequest(BaseModel):
    """Login request body."""

    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response body."""

    token: str
    username: str


class MeResponse(BaseModel):
    """Current user response body."""

    username: str
    created_at: str


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


def _normalise_labels(labels: list[str]) -> list[str]:
    """Trim, deduplicate, and drop empty labels while preserving order."""
    seen: dict[str, None] = {}
    for label in labels:
        cleaned = label.strip()
        if cleaned and cleaned not in seen:
            seen[cleaned] = None
    return list(seen.keys())


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
    secret = _get_jwt_secret()
    try:
        payload = verify_token(token, secret=secret)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    return payload["sub"]


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(request: LoginRequest, store: RemoteStore = Depends(get_store)) -> LoginResponse:
    """Authenticate a user and return a JWT token.

    Args:
        request: Login credentials.
        store: The remote store dependency.

    Returns:
        A LoginResponse with a signed JWT and the username.

    Raises:
        HTTPException: With status 401 if credentials are invalid.
    """
    user = store.get_user(request.username)
    if user is None or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_token(request.username, secret=_get_jwt_secret())
    return LoginResponse(token=token, username=request.username)


@router.get("/me")
def me(username: str = Depends(get_current_user), store: RemoteStore = Depends(get_store)) -> MeResponse:
    """Return the current user's info.

    Args:
        username: The authenticated username from the JWT dependency.
        store: The remote store dependency.

    Returns:
        A MeResponse with the user's username and creation timestamp.

    Raises:
        HTTPException: With status 404 if the user no longer exists.
    """
    user = store.get_user(username)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return MeResponse(username=user["username"], created_at=user["created_at"])


def _require_user_id(store: RemoteStore, username: str) -> int:
    """Return the integer user id for the authenticated caller.

    Raises:
        HTTPException: 404 if the user record has been removed while the JWT remains valid.
    """
    user = store.get_user(username)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return int(user["id"])


@router.post("/api-keys", status_code=201)
def create_api_key_route(
    request: CreateApiKeyRequest,
    username: str = Depends(get_current_user),
    store: RemoteStore = Depends(get_store),
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
    user_id = _require_user_id(store, username)
    if store.count_active_api_keys_for_user(user_id) >= MAX_ACTIVE_API_KEYS_PER_USER:
        raise HTTPException(
            status_code=409,
            detail=f"Maximum of {MAX_ACTIVE_API_KEYS_PER_USER} active API keys per user",
        )
    plaintext = generate_plaintext()
    expires_at = (datetime.now(UTC) + duration).isoformat()
    row = store.create_api_key(
        key_id=uuid.uuid4().hex,
        user_id=user_id,
        name=request.name,
        labels=_normalise_labels(request.labels),
        key_prefix=token_prefix(plaintext),
        key_hash=hash_token(plaintext, pepper=pepper),
        ttl=request.ttl,
        expires_at=expires_at,
    )
    public = _to_public(row)
    return CreateApiKeyResponse(**public.model_dump(), token=plaintext)


@router.get("/api-keys")
def list_api_keys_route(
    username: str = Depends(get_current_user),
    store: RemoteStore = Depends(get_store),
) -> list[ApiKeyPublic]:
    """Return the authenticated user's API keys. Never returns plaintext."""
    user_id = _require_user_id(store, username)
    return [_to_public(row) for row in store.list_api_keys_for_user(user_id)]


@router.delete("/api-keys/{key_id}", status_code=204)
def revoke_api_key_route(
    key_id: str,
    username: str = Depends(get_current_user),
    store: RemoteStore = Depends(get_store),
) -> None:
    """Revoke the given API key if it belongs to the caller.

    Revocation is idempotent: revoking a key that is already revoked returns
    204. A 404 is returned only when the key does not exist or is owned by
    a different user (uniform response, no enumeration oracle).
    """
    user_id = _require_user_id(store, username)
    if store.get_api_key_for_user(user_id=user_id, key_id=key_id) is None:
        raise HTTPException(status_code=404, detail="API key not found")
    store.revoke_api_key(user_id=user_id, key_id=key_id)
