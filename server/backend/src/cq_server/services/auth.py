"""Auth service: password-credential login → JWT issuance."""

from __future__ import annotations

from ..auth import create_token, hash_password, verify_password
from ..exceptions import InvalidCredentialsError
from ..models.auth import LoginResponse
from ..repositories import UserRepository

# Bcrypt hash verified against when the username is unknown, so login costs a
# bcrypt check whether or not the user exists. Computed via ``hash_password``
# so it always matches the work factor of real password hashes.
_DUMMY_PASSWORD_HASH = hash_password("cq-timing-equalization-dummy")


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
        if user is None:
            # Burn a bcrypt verify so unknown usernames take as long as wrong
            # passwords; otherwise response timing reveals which usernames
            # exist (username enumeration).
            verify_password(password, _DUMMY_PASSWORD_HASH)
            raise InvalidCredentialsError()
        if not verify_password(password, user["password_hash"]):
            raise InvalidCredentialsError()
        token = create_token(username, secret=self._jwt_secret)
        return LoginResponse(token=token, username=username)
