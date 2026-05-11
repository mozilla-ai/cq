"""Auth routes: session lifecycle (login today; refresh/logout forward-looking)."""

from fastapi import APIRouter

from ...models.auth import LoginRequest, LoginResponse
from ..deps import AuthServiceDep

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(request: LoginRequest, auth: AuthServiceDep) -> LoginResponse:
    """Authenticate a user and return a JWT token.

    Args:
        request: Login credentials.
        auth: The auth service dependency.

    Returns:
        A LoginResponse with a signed JWT and the username.

    Raises:
        HTTPException: With status 401 if credentials are invalid (raised
            from inside ``AuthService.login``).
    """
    return await auth.login(request.username, request.password)
