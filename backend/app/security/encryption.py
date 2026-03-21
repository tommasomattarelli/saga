"""AES-256-GCM encryption for API keys with proper key derivation."""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings

# Fixed, non-secret info string that binds the derived key to this purpose.
# Changing this value would invalidate all existing encrypted keys.
_HKDF_INFO = b"saga-api-key-encryption-v1"


def _derive_key() -> bytes:
    """Derive a 32-byte AES key from the raw secret using HKDF-SHA256.

    HKDF is a standards-compliant key derivation function (RFC 5869).
    It stretches or compresses the input material to exactly 32 bytes
    with proper entropy distribution — unlike simple truncation/padding,
    a short or predictable secret does not produce a weak key structure.

    The ``salt`` parameter is intentionally omitted (defaults to a
    hash-length zero string per RFC 5869 §2.2) — callers should ensure
    ``api_key_encryption_key`` has at least 128 bits of entropy.
    """
    raw = settings.api_key_encryption_key.encode("utf-8")
    hkdf = HKDF(algorithm=SHA256(), length=32, salt=None, info=_HKDF_INFO)
    return hkdf.derive(raw)


def encrypt_api_key(plaintext: str) -> str:
    """Encrypt an API key using AES-256-GCM.

    Output format: base64(nonce[12] || ciphertext+tag)
    The GCM tag is appended automatically by the AESGCM primitive.
    """
    key = _derive_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_api_key(encrypted: str) -> str:
    """Decrypt an API key encrypted by ``encrypt_api_key``."""
    key = _derive_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(encrypted)
    nonce = raw[:12]
    ciphertext = raw[12:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
