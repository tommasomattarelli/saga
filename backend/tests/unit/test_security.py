"""Unit tests for app/security/encryption.py."""

from __future__ import annotations

from app.security.encryption import decrypt_api_key, encrypt_api_key


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "sk-test-api-key-12345"
        encrypted = encrypt_api_key(plaintext)
        assert decrypt_api_key(encrypted) == plaintext

    def test_encrypted_value_differs_from_plaintext(self):
        plaintext = "my-secret-key"
        encrypted = encrypt_api_key(plaintext)
        assert encrypted != plaintext

    def test_encrypted_is_base64_string(self):
        import base64
        plaintext = "test-key"
        encrypted = encrypt_api_key(plaintext)
        # Should not raise
        decoded = base64.b64decode(encrypted)
        assert len(decoded) > 12  # nonce(12) + at least some ciphertext

    def test_different_calls_produce_different_ciphertext(self):
        plaintext = "same-key"
        enc1 = encrypt_api_key(plaintext)
        enc2 = encrypt_api_key(plaintext)
        # Different nonces → different ciphertext
        assert enc1 != enc2

    def test_both_encrypt_and_decrypt_to_same_value(self):
        values = ["openai-sk-abc", "anthropic-key-xyz", "short", "a" * 200]
        for v in values:
            assert decrypt_api_key(encrypt_api_key(v)) == v

    def test_empty_string_roundtrip(self):
        assert decrypt_api_key(encrypt_api_key("")) == ""
