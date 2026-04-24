"""Tests for API key token encoding and hashing."""

import uuid

import pytest

from cq_server.api_keys import (
    TOKEN_NAMESPACE,
    TOKEN_VERSION,
    decode_token,
    encode_token,
    generate_secret,
    hash_secret,
    secret_prefix,
)


class TestGenerateSecret:
    def test_is_unique(self) -> None:
        secrets_set = {generate_secret() for _ in range(100)}
        assert len(secrets_set) == 100

    def test_length(self) -> None:
        # 52 base32 characters encode 32 bytes (256 bits) without padding.
        assert len(generate_secret()) == 52

    def test_body_is_lowercase_base32(self) -> None:
        body = generate_secret()
        assert body == body.lower()
        assert set(body).issubset(set("abcdefghijklmnopqrstuvwxyz234567"))  # pragma: allowlist secret


class TestEncodeToken:
    def test_format(self) -> None:
        key_id = uuid.UUID("11111111222233334444555566667777")
        token = encode_token(key_id=key_id, secret="sekret")
        assert token == f"{TOKEN_NAMESPACE}.{TOKEN_VERSION}.{key_id.hex}.sekret"

    def test_round_trip(self) -> None:
        key_id = uuid.uuid4()
        secret = generate_secret()
        decoded_id, decoded_secret = decode_token(encode_token(key_id=key_id, secret=secret))
        assert decoded_id == key_id
        assert decoded_secret == secret


class TestDecodeToken:
    def test_rejects_wrong_part_count(self) -> None:
        with pytest.raises(ValueError):
            decode_token("cqa.v1.deadbeef")

    def test_rejects_wrong_namespace(self) -> None:
        with pytest.raises(ValueError):
            decode_token(f"other.{TOKEN_VERSION}.{uuid.uuid4().hex}.sekret")

    def test_rejects_wrong_version(self) -> None:
        with pytest.raises(ValueError):
            decode_token(f"{TOKEN_NAMESPACE}.v0.{uuid.uuid4().hex}.sekret")

    def test_rejects_empty_secret(self) -> None:
        with pytest.raises(ValueError):
            decode_token(f"{TOKEN_NAMESPACE}.{TOKEN_VERSION}.{uuid.uuid4().hex}.")

    def test_rejects_bad_uuid(self) -> None:
        valid_secret = "a" * 52
        with pytest.raises(ValueError):
            decode_token(f"{TOKEN_NAMESPACE}.{TOKEN_VERSION}.not-a-uuid.{valid_secret}")

    def test_rejects_secret_wrong_length(self) -> None:
        short = "a" * 10
        long = "a" * 100
        with pytest.raises(ValueError):
            decode_token(f"{TOKEN_NAMESPACE}.{TOKEN_VERSION}.{uuid.uuid4().hex}.{short}")
        with pytest.raises(ValueError):
            decode_token(f"{TOKEN_NAMESPACE}.{TOKEN_VERSION}.{uuid.uuid4().hex}.{long}")

    def test_rejects_secret_bad_charset(self) -> None:
        # Uppercase is outside the lowercase base32 alphabet.
        bad = "A" * 52
        with pytest.raises(ValueError):
            decode_token(f"{TOKEN_NAMESPACE}.{TOKEN_VERSION}.{uuid.uuid4().hex}.{bad}")


class TestHashSecret:
    def test_deterministic(self) -> None:
        assert hash_secret("xyz", pepper="p") == hash_secret("xyz", pepper="p")

    def test_different_peppers_produce_different_hashes(self) -> None:
        assert hash_secret("xyz", pepper="p1") != hash_secret("xyz", pepper="p2")

    def test_different_secrets_produce_different_hashes(self) -> None:
        assert hash_secret("a", pepper="p") != hash_secret("b", pepper="p")

    def test_hex_length(self) -> None:
        digest = hash_secret("xyz", pepper="p")
        assert len(digest) == 64
        int(digest, 16)  # Raises if not valid hex.


class TestSecretPrefix:
    def test_first_eight_chars(self) -> None:
        assert secret_prefix("abcdefghijklmnop") == "abcdefgh"

    def test_exact_eight(self) -> None:
        assert secret_prefix("12345678") == "12345678"
