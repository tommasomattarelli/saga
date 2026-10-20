"""Read-only instance policy the settings UI renders (ADR 0018, point 6)."""

import pytest
from httpx import AsyncClient

from app.ai.embedding_config import get_embedding_default_space
from app.ai.router import get_allowed_providers, get_instance_default, get_local_endpoints


async def test_settings_expose_read_only_policy(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/settings")
    assert response.status_code == 200
    policy = response.json()["policy"]

    default = get_instance_default()
    embedding_default = get_embedding_default_space()

    assert policy["allowed_providers"] == get_allowed_providers()
    assert policy["local_endpoints"] == sorted(get_local_endpoints())
    assert policy["generation_default"]["provider"] == default.provider
    assert policy["generation_default"]["model"] == default.model
    assert policy["embedding_default"]["provider"] == embedding_default.provider
    assert policy["embedding_default"]["model"] == embedding_default.model
    assert policy["embedding_default"]["local_endpoint"] == embedding_default.endpoint_name
    assert set(policy["server_key_sharing"]) == {
        provider for provider in get_allowed_providers() if provider != "local"
    }
    assert all(isinstance(shared, bool) for shared in policy["server_key_sharing"].values())


async def test_policy_local_endpoints_are_names_only(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/settings")
    policy = response.json()["policy"]

    assert policy["local_endpoints"]
    for name in policy["local_endpoints"]:
        assert "://" not in name
        assert ":" not in name
    assert "http" not in response.text


async def test_policy_carries_no_key_material(auth_client: AsyncClient) -> None:
    await auth_client.put("/api/settings/api-keys", json={"openai": "sk-secret-value"})

    response = await auth_client.get("/api/settings")

    assert "sk-secret-value" not in response.text
    assert "openai_api_key" not in response.text


async def test_policy_follows_the_instance_allowlist(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.settings.get_allowed_providers", lambda: ["google"])

    response = await auth_client.get("/api/settings")

    assert response.json()["policy"]["allowed_providers"] == ["google"]
    assert set(response.json()["policy"]["server_key_sharing"]) == {"google"}
