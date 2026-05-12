"""Tests for ``APIKeyService.authenticate`` and API-key usage touch behavior."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from cq_server.api_keys import encode_token, generate_secret, hash_secret
from cq_server.exceptions import APIKeyInvalidError
from cq_server.services.api_keys import APIKeyService

PEPPER = "test-pepper"


class _StubAPIKeyRepo:
    """Minimal API-key repository stub exposing only the methods the service calls."""

    def __init__(self, rows: dict[str, dict[str, Any]] | None = None) -> None:
        self.rows = rows or {}
        self.touched: list[str] = []

    async def get_active_by_id(self, key_id: str) -> dict[str, Any] | None:
        row = self.rows.get(key_id)
        if row is None or row.get("revoked_at") is not None:
            return None
        if datetime.fromisoformat(row["expires_at"]) <= datetime.now(UTC):
            return None
        return row

    async def touch_last_used(self, key_id: str) -> None:
        self.touched.append(key_id)


class _StubUserRepo:
    """``UserRepository`` stub; ``authenticate`` never calls into it."""

    async def get(self, username: str) -> None:
        return None


def _row(
    *,
    key_id: uuid.UUID,
    secret: str,
    username: str = "alice",
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "id": key_id.hex,
        "user_id": 1,
        "username": username,
        "name": "l",
        "labels": [],
        "key_prefix": secret[:8],
        "key_hash": hash_secret(secret, pepper=PEPPER),
        "ttl": "30d",
        "expires_at": (expires_at or datetime.now(UTC) + timedelta(days=30)).isoformat(),
        "created_at": datetime.now(UTC).isoformat(),
        "last_used_at": None,
        "revoked_at": revoked_at.isoformat() if revoked_at else None,
    }


def _make_service(repo: _StubAPIKeyRepo, *, pepper: str = PEPPER) -> APIKeyService:
    """Compose ``APIKeyService`` over the stub repositories for unit testing."""
    return APIKeyService(api_keys=repo, users=_StubUserRepo(), pepper=pepper)  # type: ignore[arg-type]


class TestAuthenticateHappyPath:
    async def test_valid_token_returns_username_and_key_id(self) -> None:
        key_id = uuid.uuid4()
        secret = generate_secret()
        repo = _StubAPIKeyRepo({key_id.hex: _row(key_id=key_id, secret=secret)})
        token = encode_token(key_id=key_id, secret=secret)
        service = _make_service(repo)

        username, touched_key_id = await service.authenticate(token)

        assert username == "alice"
        assert touched_key_id == key_id.hex

    async def test_touch_last_used_updates_repository(self) -> None:
        key_id = uuid.uuid4()
        secret = generate_secret()
        repo = _StubAPIKeyRepo({key_id.hex: _row(key_id=key_id, secret=secret)})
        service = _make_service(repo)

        await service.touch_last_used(key_id.hex)

        assert repo.touched == [key_id.hex]


class TestAuthenticateRejections:
    async def test_wrong_namespace(self) -> None:
        service = _make_service(_StubAPIKeyRepo())
        token = f"sk.v1.{uuid.uuid4().hex}.sekret"
        with pytest.raises(APIKeyInvalidError):
            await service.authenticate(token)

    async def test_malformed_token(self) -> None:
        service = _make_service(_StubAPIKeyRepo())
        with pytest.raises(APIKeyInvalidError):
            await service.authenticate("cqa_legacy")

    async def test_unknown_key_id(self) -> None:
        service = _make_service(_StubAPIKeyRepo())
        token = encode_token(key_id=uuid.uuid4(), secret=generate_secret())
        with pytest.raises(APIKeyInvalidError):
            await service.authenticate(token)

    async def test_wrong_secret(self) -> None:
        key_id = uuid.uuid4()
        stored_secret = generate_secret()
        repo = _StubAPIKeyRepo({key_id.hex: _row(key_id=key_id, secret=stored_secret)})
        presented = encode_token(key_id=key_id, secret=generate_secret())
        service = _make_service(repo)
        with pytest.raises(APIKeyInvalidError):
            await service.authenticate(presented)

    async def test_revoked_token(self) -> None:
        key_id = uuid.uuid4()
        secret = generate_secret()
        repo = _StubAPIKeyRepo({key_id.hex: _row(key_id=key_id, secret=secret, revoked_at=datetime.now(UTC))})
        token = encode_token(key_id=key_id, secret=secret)
        service = _make_service(repo)
        with pytest.raises(APIKeyInvalidError):
            await service.authenticate(token)

    async def test_expired_token(self) -> None:
        key_id = uuid.uuid4()
        secret = generate_secret()
        row = _row(key_id=key_id, secret=secret, expires_at=datetime.now(UTC) - timedelta(seconds=1))
        repo = _StubAPIKeyRepo({key_id.hex: row})
        token = encode_token(key_id=key_id, secret=secret)
        service = _make_service(repo)
        with pytest.raises(APIKeyInvalidError):
            await service.authenticate(token)
