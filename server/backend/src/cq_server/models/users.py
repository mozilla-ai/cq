"""Pydantic schemas for /users routes (current user, API keys)."""

from pydantic import BaseModel, Field


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


class ApiKeysPublic(BaseModel):
    """Collection wrapper for API key listings.

    The envelope shape leaves room for pagination metadata (e.g. a
    ``next_cursor`` field) without breaking existing clients.
    """

    data: list[ApiKeyPublic]
    count: int


class CreateApiKeyRequest(BaseModel):
    """Request body for creating an API key."""

    name: str = Field(min_length=1, max_length=64)
    ttl: str = Field(min_length=1, max_length=16)
    labels: list[str] = Field(default_factory=list, max_length=16)


class CreateApiKeyResponse(ApiKeyPublic):
    """Create response; the plaintext ``token`` is returned exactly once."""

    token: str


class MeResponse(BaseModel):
    """Current user response body."""

    username: str
    created_at: str


class Message(BaseModel):
    """Generic message response body."""

    message: str
