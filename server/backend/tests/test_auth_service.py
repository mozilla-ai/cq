"""Unit tests for ``AuthService`` service-layer behavior."""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

from cq_server.auth import hash_password, verify_password
from cq_server.exceptions import InvalidCredentialsError
from cq_server.services.auth import _DUMMY_PASSWORD_HASH, AuthService


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

    async def test_login_verifies_password_even_for_unknown_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An unknown username must still cost a password verify.

        Unequal cost would let response timing reveal which usernames exist.
        """
        verify = Mock(return_value=True)
        monkeypatch.setattr("cq_server.services.auth.verify_password", verify)
        service = AuthService(users=_StubUserRepo(None), jwt_secret="test-secret")  # type: ignore[arg-type]

        with pytest.raises(InvalidCredentialsError):
            await service.login("nobody", "secret123")

        verify.assert_called_once_with("secret123", _DUMMY_PASSWORD_HASH)

    async def test_login_raises_invalid_credentials_for_wrong_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stored_hash = hash_password("secret123")
        repo = _StubUserRepo({"username": "alice", "password_hash": stored_hash})
        service = AuthService(users=repo, jwt_secret="test-secret")  # type: ignore[arg-type]
        verify = Mock(wraps=verify_password)
        monkeypatch.setattr("cq_server.services.auth.verify_password", verify)

        with pytest.raises(InvalidCredentialsError):
            await service.login("alice", "wrong")

        verify.assert_called_once_with("wrong", stored_hash)

    async def test_login_for_unknown_user_never_creates_a_hash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The first unknown-username login must cost the same as every later one."""
        monkeypatch.setattr("cq_server.auth.bcrypt.hashpw", Mock(side_effect=AssertionError("hash created")))
        service = AuthService(users=_StubUserRepo(None), jwt_secret="test-secret")  # type: ignore[arg-type]

        with pytest.raises(InvalidCredentialsError):
            await service.login("nobody", "secret123")


def _bcrypt_variant_and_cost(hashed: str) -> list[str]:
    return hashed.split("$")[1:3]


def test_dummy_hash_work_factor_matches_hash_password() -> None:
    assert _bcrypt_variant_and_cost(_DUMMY_PASSWORD_HASH) == _bcrypt_variant_and_cost(hash_password("x"))
