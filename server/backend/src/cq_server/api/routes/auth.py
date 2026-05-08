"""Auth routes: session lifecycle (login today; refresh/logout forward-looking)."""

from fastapi import APIRouter, Depends, HTTPException

from ...auth import create_token, verify_password
from ...models.auth import LoginRequest, LoginResponse
from ...store import Store
from ..deps import _get_jwt_secret, get_store

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(request: LoginRequest, store: Store = Depends(get_store)) -> LoginResponse:
    """Authenticate a user and return a JWT token.

    Args:
        request: Login credentials.
        store: The store dependency.

    Returns:
        A LoginResponse with a signed JWT and the username.

    Raises:
        HTTPException: With status 401 if credentials are invalid.
    """
    user = await store.get_user(request.username)
    if user is None or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_token(request.username, secret=_get_jwt_secret())
    return LoginResponse(token=token, username=request.username)
