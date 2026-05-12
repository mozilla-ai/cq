"""Auth service: password-credential login → JWT issuance."""

from __future__ import annotations

from ..auth import create_token, verify_password
from ..exceptions import InvalidCredentialsError
from ..models.auth import LoginResponse
from ..repositories import UserRepository


class AuthService:
    """Validate user credentials and issue JWTs."""

    def __init__(self, *, users: UserRepository, jwt_secret: str) -> None:
        """Compose the auth service over the user repository and the signing secret."""
        self._users = users
        self._jwt_secret = jwt_secret

    async def login(self, username: str, password: str) -> LoginResponse:
        """Authenticate ``username``/``password`` and return a fresh ``LoginResponse``.

        Raises:
            InvalidCredentialsError: If credentials do not match a user.
        """
        user = await self._users.get(username)
        if user is None or not verify_password(password, user["password_hash"]):
            raise InvalidCredentialsError()
        token = create_token(username, secret=self._jwt_secret)
        return LoginResponse(token=token, username=username)
