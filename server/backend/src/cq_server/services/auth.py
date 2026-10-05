"""Auth service: password-credential login → JWT issuance."""

from __future__ import annotations

import asyncio

from ..auth import create_token, verify_password
from ..exceptions import InvalidCredentialsError
from ..models.auth import LoginResponse
from ..repositories import UserRepository

# NOTE: This hash's work factor must equal the one hash_password uses.
_DUMMY_PASSWORD_HASH = "$2b$12$.Os6vNMQhvC54r..M0HpC../JpIm.DBbugKLmxjtbgRXOsMpz5I1e"  # pragma: allowlist secret


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
        # Verifying a dummy hash keeps login timing independent of whether the username exists.
        hashed = _DUMMY_PASSWORD_HASH if user is None else user["password_hash"]
        password_matches = await asyncio.to_thread(verify_password, password, hashed)
        if user is None or not password_matches:
            raise InvalidCredentialsError()
        token = create_token(username, secret=self._jwt_secret)
        return LoginResponse(token=token, username=username)
