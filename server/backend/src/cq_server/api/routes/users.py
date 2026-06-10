"""User-owned resources: the current user record and their API keys."""

from fastapi import APIRouter, HTTPException, status

from ...exceptions import (
    APIKeyActiveLimitReachedError,
    APIKeyNotFoundError,
    APIKeyTTLInvalidError,
    ServiceError,
    UserNotFoundError,
)
from ...models.users import (
    ApiKeyList,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    MeResponse,
    Message,
)
from ..deps import APIKeyServiceDep, CurrentUserDep, UserRepositoryDep

router = APIRouter(prefix="/users", tags=["users"])


def user_exception_mappings() -> dict[type[ServiceError], int]:
    """Return service-exception to HTTP-status mappings for user routes."""
    return {
        APIKeyActiveLimitReachedError: status.HTTP_409_CONFLICT,
        APIKeyNotFoundError: status.HTTP_404_NOT_FOUND,
        APIKeyTTLInvalidError: status.HTTP_422_UNPROCESSABLE_CONTENT,
        UserNotFoundError: status.HTTP_404_NOT_FOUND,
    }


@router.get("/me")
async def me(username: CurrentUserDep, users: UserRepositoryDep) -> MeResponse:
    """Return the current user's info.

    Raises:
        HTTPException: 404 if the user record has been removed while the JWT
            remains valid.
    """
    user = await users.get(username)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return MeResponse(username=user["username"], created_at=user["created_at"])


@router.post("/me/api-keys", status_code=201)
async def create_api_key_route(
    request: CreateApiKeyRequest,
    username: CurrentUserDep,
    api_keys: APIKeyServiceDep,
) -> CreateApiKeyResponse:
    """Create a new API key owned by the authenticated user.

    The plaintext ``token`` is returned exactly once, in this response. It
    cannot be retrieved afterwards; if the caller loses it, they must revoke
    and create a new key.

    Raises:
        HTTPException: 422 if the TTL is invalid, 409 if the user already has
            the maximum number of active keys.
    """
    return await api_keys.create(
        username=username,
        name=request.name,
        ttl=request.ttl,
        labels=request.labels,
    )


@router.get("/me/api-keys")
async def list_api_keys_route(
    username: CurrentUserDep,
    api_keys: APIKeyServiceDep,
) -> ApiKeyList:
    """Return the authenticated user's API keys. Never returns plaintext.

    Revoked keys are included with ``is_active: false`` so users can audit
    their own revocation history.
    """
    return await api_keys.list_for_user(username)


@router.post("/me/api-keys/{key_id}/revoke")
async def revoke_api_key_route(
    key_id: str,
    username: CurrentUserDep,
    api_keys: APIKeyServiceDep,
) -> Message:
    """Revoke the given API key if it belongs to the caller.

    Revocation is a state transition; the row is retained with
    ``revoked_at`` set. Repeated revocations are idempotent and succeed.
    A 404 is returned when the key does not exist or is owned by a
    different user (uniform response, no enumeration oracle).
    """
    return await api_keys.revoke(username=username, key_id=key_id)
