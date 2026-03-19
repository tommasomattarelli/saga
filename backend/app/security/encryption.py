"""AES-256 encryption for API keys."""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


def _get_key() -> bytes:
    """Derive 32-byte key from settings."""
    raw = settings.api_key_encryption_key.encode("utf-8")
    # Pad or truncate to 32 bytes
    return raw.ljust(32, b"\0")[:32]


def encrypt_api_key(plaintext: str) -> str:
    """Encrypt an API key using AES-256-GCM."""
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # Encode nonce + ciphertext as base64
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_api_key(encrypted: str) -> str:
    """Decrypt an API key."""
    key = _get_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(encrypted)
    nonce = raw[:12]
    ciphertext = raw[12:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
