"""Unit tests for ``AuthService`` service-layer behavior."""

from __future__ import annotations

from typing import Any

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
        """Unknown usernames must still cost a bcrypt verify (no timing oracle)."""
        hashes_checked: list[str] = []

        def _recording_verify(password: str, hashed: str) -> bool:
            hashes_checked.append(hashed)
            return True  # even a "passing" dummy verify must not log in

        monkeypatch.setattr("cq_server.services.auth.verify_password", _recording_verify)
        service = AuthService(users=_StubUserRepo(None), jwt_secret="test-secret")  # type: ignore[arg-type]

        with pytest.raises(InvalidCredentialsError):
            await service.login("nobody", "secret123")

        assert hashes_checked == [_DUMMY_PASSWORD_HASH]

    async def test_login_raises_invalid_credentials_for_wrong_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stored_hash = hash_password("secret123")
        repo = _StubUserRepo({"username": "alice", "password_hash": stored_hash})
        service = AuthService(users=repo, jwt_secret="test-secret")  # type: ignore[arg-type]
        hashes_checked: list[str] = []

        def _recording_verify(password: str, hashed: str) -> bool:
            hashes_checked.append(hashed)
            return verify_password(password, hashed)

        monkeypatch.setattr("cq_server.services.auth.verify_password", _recording_verify)

        with pytest.raises(InvalidCredentialsError):
            await service.login("alice", "wrong")

        assert hashes_checked == [stored_hash]
