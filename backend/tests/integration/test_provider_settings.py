import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.security.auth import decode_token


async def test_embedding_profile_defaults_to_instance(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["embedding_provider"] is None
    assert payload["embedding_model"] is None
    assert payload["embedding_local_endpoint"] is None
    assert payload["effective_embedding_provider"] == "google"
    assert payload["embedding_credential_source"] == "missing"


async def test_personal_profiles_persist_independently(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    profile = {
        "generation_provider": "openrouter",
        "generation_model": "personal-generation",
        "embedding_provider": "local",
        "embedding_model": "personal-embedding",
        "embedding_local_endpoint": "ollama",
    }
    response = await auth_client.patch("/api/settings", json=profile)
    assert response.status_code == 200

    payload = (await auth_client.get("/api/settings")).json()
    for field, value in profile.items():
        assert payload[field] == value

    token = auth_client.headers["Authorization"].removeprefix("Bearer ")
    user = await db_session.get(
        User, uuid.UUID(str(decode_token(token)["sub"])), populate_existing=True
    )
    assert user is not None
    assert user.embedding_provider == "local"
    assert user.embedding_model == "personal-embedding"
    assert user.embedding_local_endpoint == "ollama"
    assert payload["embedding_credential_source"] == "not_required"

    response = await auth_client.patch(
        "/api/settings",
        json={field: None for field in profile if field.startswith("embedding_")},
    )
    assert response.status_code == 200
    assert response.json()["embedding_provider"] is None
    assert response.json()["embedding_model"] is None
    assert response.json()["embedding_local_endpoint"] is None
    assert response.json()["generation_model"] == "personal-generation"


@pytest.mark.parametrize("prefix", ["generation", "embedding"])
async def test_profiles_reject_disabled_providers(auth_client: AsyncClient, prefix: str) -> None:
    response = await auth_client.patch("/api/settings", json={f"{prefix}_provider": "cohere"})
    assert response.status_code == 400
    assert "not enabled" in response.json()["detail"]


@pytest.mark.parametrize("prefix", ["generation", "embedding"])
async def test_profiles_only_accept_named_local_endpoints(
    auth_client: AsyncClient, prefix: str
) -> None:
    response = await auth_client.patch(
        "/api/settings",
        json={f"{prefix}_local_endpoint": "http://169.254.169.254/"},
    )
    assert response.status_code == 400
    assert "endpoint" in response.json()["detail"].lower()


@pytest.mark.parametrize("prefix", ["generation", "embedding"])
async def test_profiles_persist_named_local_endpoints(
    auth_client: AsyncClient, prefix: str
) -> None:
    profile = {
        f"{prefix}_provider": "local",
        f"{prefix}_model": "local-model",
        f"{prefix}_local_endpoint": "ollama",
    }
    response = await auth_client.patch("/api/settings", json=profile)
    assert response.status_code == 200
    payload = (await auth_client.get("/api/settings")).json()
    for field, value in profile.items():
        assert payload[field] == value


async def test_embedding_profile_respects_instance_allowlist(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.settings.get_allowed_providers", lambda: ["google"])
    response = await auth_client.patch("/api/settings", json={"embedding_provider": "openai"})
    assert response.status_code == 400


async def test_embedding_credential_provenance_uses_its_own_provider(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.put(
        "/api/settings/api-keys", json={"openrouter": "personal-embedding-key"}
    )
    assert response.status_code == 200

    response = await auth_client.patch(
        "/api/settings",
        json={
            "generation_provider": "google",
            "generation_model": "generation",
            "embedding_provider": "openrouter",
            "embedding_model": "embedding",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["credential_source"] == "missing"
    assert payload["embedding_credential_source"] == "personal"
    assert "personal-embedding-key" not in response.text
