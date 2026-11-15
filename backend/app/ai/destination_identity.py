"""Opaque destination identities for generation format consent."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings

_FINGERPRINT_VERSION = "v1"
_HKDF_INFO = b"saga-generation-destination-v1"


def destination_fingerprint(
    *,
    provider: str,
    model: str,
    endpoint: str,
    mode: str | None,
) -> str:
    payload = json.dumps(
        {
            "provider": provider,
            "model": model,
            "endpoint": endpoint,
            "mode": mode,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    key = HKDF(
        algorithm=SHA256(),
        length=32,
        salt=None,
        info=_HKDF_INFO,
    ).derive(settings.api_key_encryption_key.encode("utf-8"))
    digest = hmac.new(key, payload, hashlib.sha256).digest()
    encoded_digest = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{_FINGERPRINT_VERSION}:{encoded_digest}"
