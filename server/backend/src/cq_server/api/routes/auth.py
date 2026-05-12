"""Auth routes: session lifecycle (login today; refresh/logout forward-looking)."""

from fastapi import APIRouter, status

from ...exceptions import InvalidCredentialsError, ServiceError
from ...models.auth import LoginRequest, LoginResponse
from ..deps import AuthServiceDep

router = APIRouter(prefix="/auth", tags=["auth"])


def auth_exception_mappings() -> dict[type[ServiceError], int]:
    """Return service-exception to HTTP-status mappings for auth routes."""
    return {
        InvalidCredentialsError: status.HTTP_401_UNAUTHORIZED,
    }


@router.post("/login")
async def login(request: LoginRequest, auth: AuthServiceDep) -> LoginResponse:
    """Authenticate a user and return a JWT token.

    Args:
        request: Login credentials.
        auth: The auth service dependency.

    Returns:
        A LoginResponse with a signed JWT and the username.

    Raises:
        InvalidCredentialsError: If credentials are invalid.
    """
    return await auth.login(request.username, request.password)
