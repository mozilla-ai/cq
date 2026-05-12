"""Unit tests for ``AuthService`` service-layer behavior."""

from __future__ import annotations

from typing import Any

import pytest

from cq_server.auth import hash_password
from cq_server.exceptions import InvalidCredentialsError
from cq_server.services.auth import AuthService


class _StubUserRepo:
    """Minimal user repository stub for ``AuthService`` tests."""

    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    async def get(self, username: str) -> dict[str, Any] | None:
        if self._row is None:
            return None
        if self._row["username"] != username:
            return None
        return self._row


class TestAuthServiceLogin:
    async def test_login_returns_token_for_valid_credentials(self) -> None:
        repo = _StubUserRepo({"username": "alice", "password_hash": hash_password("secret123")})
        service = AuthService(users=repo, jwt_secret="test-secret")  # type: ignore[arg-type]

        response = await service.login("alice", "secret123")

        assert response.username == "alice"
        assert isinstance(response.token, str)
        assert response.token

    async def test_login_raises_invalid_credentials_for_unknown_user(self) -> None:
        service = AuthService(users=_StubUserRepo(None), jwt_secret="test-secret")  # type: ignore[arg-type]

        with pytest.raises(InvalidCredentialsError):
            await service.login("nobody", "secret123")

    async def test_login_raises_invalid_credentials_for_wrong_password(self) -> None:
        repo = _StubUserRepo({"username": "alice", "password_hash": hash_password("secret123")})
        service = AuthService(users=repo, jwt_secret="test-secret")  # type: ignore[arg-type]

        with pytest.raises(InvalidCredentialsError):
            await service.login("alice", "wrong")
