import pytest
from starlette.requests import Request

from app.config import settings
from app.security.encryption import decrypt_api_key


@pytest.mark.parametrize(
    "host",
    [b"example.com/allowed?bar=", b"example.com#fragment", b"example.com?query="],
)
def test_malformed_host_cannot_change_request_url_path(host: bytes) -> None:
    request = Request(
        {
            "type": "http",
            "scheme": "http",
            "server": ("saga.test", 8000),
            "path": "/api/campaigns",
            "query_string": b"",
            "headers": [(b"host", host)],
        }
    )

    assert request.url.path == "/api/campaigns"
    assert request.url.query == ""


def test_existing_encrypted_provider_key_survives_crypto_upgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings, "api_key_encryption_key", "saga-crypto-upgrade-compatibility-key"
    )
    encrypted = "AAECAwQFBgcICQoLfTQbzXrlfNXtFhQkWHnIbANj0s9Dxa/PUDwzW5CafnivJW59SgpO+VteeiR1ug=="

    assert decrypt_api_key(encrypted) == "sk-existing-key-before-upgrade"
