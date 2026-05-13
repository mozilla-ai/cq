"""API-key service: token authentication, issuance, listing, revocation."""

from __future__ import annotations

import hmac
import uuid
from datetime import UTC, datetime
from typing import Any

from cq.ttl import TTLError
from cq.ttl import parse as parse_ttl

from ..api_keys import decode_token, encode_token, generate_secret, hash_secret, secret_prefix
from ..exceptions import (
    APIKeyActiveLimitReachedError,
    APIKeyInvalidError,
    APIKeyNotFoundError,
    APIKeyTTLInvalidError,
    UserNotFoundError,
)
from ..models.users import (
    ApiKeyPublic,
    ApiKeysPublic,
    CreateApiKeyResponse,
    Message,
)
from ..repositories import APIKeyRepository, UserRepository

MAX_ACTIVE_API_KEYS_PER_USER = 20


class APIKeyService:
    """Compose API-key persistence with token validation, issuance, and revocation."""

    def __init__(
        self,
        *,
        api_keys: APIKeyRepository,
        users: UserRepository,
        pepper: str,
    ) -> None:
        """Compose the service over its repositories and the API-key pepper."""
        self._api_keys = api_keys
        self._users = users
        self._pepper = pepper

    async def authenticate(self, token: str) -> tuple[str, str]:
        """Validate ``token`` and return ``(username, key_id)``.

        Raises:
            APIKeyInvalidError: On any decode/lookup/HMAC failure.
        """
        try:
            key_id, secret = decode_token(token)
        except ValueError as exc:
            raise APIKeyInvalidError() from exc
        row = await self._api_keys.get_active_by_id(key_id.hex)
        if row is None:
            raise APIKeyInvalidError()
        if not hmac.compare_digest(row["key_hash"], hash_secret(secret, pepper=self._pepper)):
            raise APIKeyInvalidError()
        return row["username"], row["id"]

    async def touch_last_used(self, key_id: str) -> None:
        """Record that API key ``key_id`` was used."""
        await self._api_keys.touch_last_used(key_id)

    async def create(
        self,
        *,
        username: str,
        name: str,
        ttl: str,
        labels: list[str],
    ) -> CreateApiKeyResponse:
        """Issue a new API key for ``username`` and return it with plaintext.

        Raises:
            APIKeyTTLInvalidError: If the TTL is malformed.
            APIKeyActiveLimitReachedError: If the user is already at the active-key cap.
        """
        try:
            canonical_ttl, duration = parse_ttl(ttl)
        except TTLError as exc:
            raise APIKeyTTLInvalidError(str(exc)) from exc
        user_id = await self._require_user_id(username)
        if await self._api_keys.count_active_for_user(user_id) >= MAX_ACTIVE_API_KEYS_PER_USER:
            raise APIKeyActiveLimitReachedError(MAX_ACTIVE_API_KEYS_PER_USER)
        key_id = uuid.uuid4()
        secret = generate_secret()
        plaintext = encode_token(key_id=key_id, secret=secret)
        expires_at = (datetime.now(UTC) + duration).isoformat()
        # Persist the canonical (lower-case, trimmed) TTL so non-CLI
        # clients that submit "30D" or "  30d  " round-trip identically
        # to clients that already canonicalise client-side.
        row = await self._api_keys.create(
            key_id=key_id.hex,
            user_id=user_id,
            name=name,
            labels=_normalise_labels(labels),
            key_prefix=secret_prefix(secret),
            key_hash=hash_secret(secret, pepper=self._pepper),
            ttl=canonical_ttl,
            expires_at=expires_at,
        )
        public = _to_public(row)
        return CreateApiKeyResponse(**public.model_dump(), token=plaintext)

    async def list_for_user(self, username: str) -> ApiKeysPublic:
        """Return every API key owned by ``username`` (including revoked rows)."""
        user_id = await self._require_user_id(username)
        data = [_to_public(row) for row in await self._api_keys.list_for_user(user_id)]
        return ApiKeysPublic(data=data, count=len(data))

    async def revoke(self, *, username: str, key_id: str) -> Message:
        """Revoke ``key_id`` if it belongs to ``username``. Idempotent.

        Returns the same 404 whether the key is unknown or owned by a
        different user, so callers can't enumerate other users' keys.
        """
        user_id = await self._require_user_id(username)
        if await self._api_keys.get_for_user(user_id=user_id, key_id=key_id) is None:
            raise APIKeyNotFoundError()
        await self._api_keys.revoke(user_id=user_id, key_id=key_id)
        return Message(message="API key revoked.")

    async def _require_user_id(self, username: str) -> int:
        user = await self._users.get(username)
        if user is None:
            raise UserNotFoundError()
        return int(user["id"])


def _normalise_labels(labels: list[str]) -> list[str]:
    """Trim, deduplicate, and drop empty labels while preserving order."""
    seen: dict[str, None] = {}
    for label in labels:
        cleaned = label.strip()
        if cleaned and cleaned not in seen:
            seen[cleaned] = None
    return list(seen.keys())


def _to_public(row: dict[str, Any]) -> ApiKeyPublic:
    """Build the public view of an API key row."""
    now = datetime.now(UTC)
    expires_at = datetime.fromisoformat(row["expires_at"])
    is_expired = expires_at <= now
    is_active = row["revoked_at"] is None and not is_expired
    return ApiKeyPublic(
        id=row["id"],
        name=row["name"],
        labels=list(row.get("labels") or []),
        prefix=row["key_prefix"],
        ttl=row["ttl"],
        expires_at=row["expires_at"],
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
        revoked_at=row["revoked_at"],
        is_expired=is_expired,
        is_active=is_active,
    )
