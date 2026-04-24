"""Tests for API key token generation and hashing."""

from cq_server.api_keys import PREFIX, generate_plaintext, hash_token, token_prefix


class TestGeneratePlaintext:
    def test_starts_with_prefix(self) -> None:
        assert generate_plaintext().startswith(PREFIX)

    def test_is_unique(self) -> None:
        tokens = {generate_plaintext() for _ in range(100)}
        assert len(tokens) == 100

    def test_length(self) -> None:
        # 4-char prefix plus 52 base32 chars for 32 bytes (256 bits) without padding.
        assert len(generate_plaintext()) == len(PREFIX) + 52

    def test_body_is_lowercase_base32(self) -> None:
        body = generate_plaintext().removeprefix(PREFIX)
        assert body == body.lower()
        assert set(body).issubset(set("abcdefghijklmnopqrstuvwxyz234567"))  # pragma: allowlist secret


class TestHashToken:
    def test_deterministic(self) -> None:
        assert hash_token("cqa_xyz", pepper="p") == hash_token("cqa_xyz", pepper="p")

    def test_different_peppers_produce_different_hashes(self) -> None:
        assert hash_token("cqa_xyz", pepper="p1") != hash_token("cqa_xyz", pepper="p2")

    def test_different_tokens_produce_different_hashes(self) -> None:
        assert hash_token("cqa_a", pepper="p") != hash_token("cqa_b", pepper="p")

    def test_hex_length(self) -> None:
        digest = hash_token("cqa_xyz", pepper="p")
        assert len(digest) == 64
        int(digest, 16)  # Raises if not valid hex.


class TestTokenPrefix:
    def test_first_eight_chars(self) -> None:
        assert token_prefix("cqa_abcdefg") == "cqa_abcd"

    def test_exact_eight(self) -> None:
        assert token_prefix("12345678") == "12345678"
