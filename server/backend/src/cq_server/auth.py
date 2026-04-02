"""Authentication: password hashing, JWT creation and validation."""

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .deps import get_store
from .store import RemoteStore


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
