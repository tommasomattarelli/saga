"""Unit tests for app/security/encryption.py and app/security/rbac.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

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


class TestRbac:
    @pytest.mark.asyncio
    async def test_require_admin_returns_user_when_admin(self):
        from app.security.rbac import require_admin

        admin_user = MagicMock()
        admin_user.is_admin = True
        result = await require_admin(user=admin_user)
        assert result is admin_user

    @pytest.mark.asyncio
    async def test_require_admin_raises_403_when_not_admin(self):
        from app.security.rbac import require_admin

        normal_user = MagicMock()
        normal_user.is_admin = False

        with pytest.raises(HTTPException) as exc_info:
            await require_admin(user=normal_user)

        assert exc_info.value.status_code == 403
        assert "Admin" in exc_info.value.detail
