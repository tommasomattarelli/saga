import base64
import hashlib
import json

import pytest

from app.ai.destination_identity import destination_fingerprint


def test_destination_fingerprint_is_versioned_opaque_hmac(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.ai.destination_identity.settings.api_key_encryption_key",
        "test-instance-identity-secret-one",
    )
    endpoint = "https://user-canary:password-canary@proxy.invalid/v1?token=query-canary"
    fingerprint = destination_fingerprint(
        provider="google",
        model="model",
        endpoint=endpoint,
        mode="vertex",
    )
    payload = json.dumps(
        {
            "endpoint": endpoint,
            "mode": "vertex",
            "model": "model",
            "provider": "google",
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    assert fingerprint.startswith("v1:")
    unkeyed_digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode("ascii")
    assert len(fingerprint) == 46
    assert unkeyed_digest.rstrip("=") != fingerprint.removeprefix("v1:")
    for secret in ("user-canary", "password-canary", "query-canary", endpoint):
        assert secret not in fingerprint


def test_destination_fingerprint_binds_full_url_provider_model_and_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.ai.destination_identity.settings.api_key_encryption_key",
        "test-instance-identity-secret",
    )
    identity = destination_fingerprint(
        provider="google",
        model="model-one",
        endpoint="https://user:token@proxy.invalid/v1?route=primary&key=secret",
        mode="vertex",
    )

    assert (
        destination_fingerprint(
            provider="google",
            model="model-one",
            endpoint="https://user:rotated@proxy.invalid/v1?route=primary&key=secret",
            mode="vertex",
        )
        != identity
    )
    assert (
        destination_fingerprint(
            provider="google",
            model="model-one",
            endpoint="https://user:token@proxy.invalid/v1?route=secondary&key=secret",
            mode="vertex",
        )
        != identity
    )
    assert (
        destination_fingerprint(
            provider="google",
            model="model-two",
            endpoint="https://user:token@proxy.invalid/v1?route=primary&key=secret",
            mode="vertex",
        )
        != identity
    )
    assert (
        destination_fingerprint(
            provider="google",
            model="model-one",
            endpoint="https://user:token@proxy.invalid/v1?route=primary&key=secret",
            mode="developer",
        )
        != identity
    )
    assert (
        destination_fingerprint(
            provider="openai",
            model="model-one",
            endpoint="https://user:token@proxy.invalid/v1?route=primary&key=secret",
            mode=None,
        )
        != identity
    )


def test_instance_identity_secret_rotation_invalidates_fingerprints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.ai.destination_identity.settings.api_key_encryption_key",
        "test-instance-identity-secret-one",
    )
    first = destination_fingerprint(
        provider="google",
        model="model",
        endpoint="https://proxy.invalid/v1",
        mode="vertex",
    )

    monkeypatch.setattr(
        "app.ai.destination_identity.settings.api_key_encryption_key",
        "test-instance-identity-secret-two",
    )
    second = destination_fingerprint(
        provider="google",
        model="model",
        endpoint="https://proxy.invalid/v1",
        mode="vertex",
    )

    assert first != second
