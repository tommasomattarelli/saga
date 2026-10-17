import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import base
from app.ai.router import get_user_generation
from app.exceptions import ValidationError
from app.models.user import User
from app.security.auth import decode_token


def user_id(client: AsyncClient) -> uuid.UUID:
    token = client.headers["Authorization"].removeprefix("Bearer ")
    return uuid.UUID(str(decode_token(token)["sub"]))


@pytest.fixture(autouse=True)
def clear_clients():
    base._providers.clear()
    yield
    base._providers.clear()


async def test_generation_uses_the_decrypted_personal_key(auth_client: AsyncClient) -> None:
    await auth_client.put("/api/settings/api-keys", json={"openai": "personal-key"})
    await auth_client.patch(
        "/api/settings",
        json={"generation_provider": "openai", "generation_model": "personal-model"},
    )
    client = AsyncMock()
    with patch("app.ai.providers.openai.OpenAIProvider", return_value=client) as factory:
        provider, config = await get_user_generation(user_id(auth_client))

    factory.assert_called_once_with(api_key="personal-key")
    assert provider is client
    assert config.provider == "openai"
    assert config.model == "personal-model"
    assert config.max_tokens == 60000


async def test_missing_key_does_not_use_an_unconsented_server_key(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.ai.credentials.settings.google_ai_api_key", "server-key")
    with pytest.raises(ValidationError, match="key"):
        await get_user_generation(user_id(auth_client))
    assert base._providers == {}


async def test_unreadable_personal_key_never_uses_server_fallback(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await db_session.get(User, user_id(auth_client))
    assert owner is not None
    owner.google_api_key_enc = "invalid-ciphertext"
    owner.server_key_consents = {"google": True}
    await db_session.commit()
    monkeypatch.setattr("app.ai.credentials.settings.google_ai_api_key", "server-key")
    monkeypatch.setattr("app.ai.credentials.get_server_key_fallback", lambda: {"google": True})

    with pytest.raises(ValidationError, match="personal key") as error:
        await get_user_generation(user_id(auth_client))
    assert "invalid-ciphertext" not in str(error.value)
    assert "server-key" not in str(error.value)


async def test_local_generation_uses_only_the_named_endpoint(auth_client: AsyncClient) -> None:
    await auth_client.patch(
        "/api/settings",
        json={
            "generation_provider": "local",
            "generation_model": "local-model",
            "generation_local_endpoint": "ollama",
        },
    )
    with patch("app.ai.providers.local.LocalProvider") as factory:
        _, config = await get_user_generation(user_id(auth_client))
    factory.assert_called_once_with(base_url="http://localhost:11434/v1", api_key=None)
    assert config.model == "local-model"


async def test_partial_personal_profile_is_rejected(auth_client: AsyncClient) -> None:
    await auth_client.patch("/api/settings", json={"generation_provider": "openai"})
    with pytest.raises(ValidationError, match="provider and.*model"):
        await get_user_generation(user_id(auth_client))


async def test_missing_credentials_reject_the_turn_before_claiming_it(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.models.campaign import Campaign

    response = await auth_client.post(
        "/api/campaigns",
        json={"world_id": "the-awakening", "name": "No credentials", "difficulty": "medium"},
    )
    assert response.status_code == 201
    campaign_id = response.json()["id"]
    response = await auth_client.post(
        f"/api/campaigns/{campaign_id}/action", json={"action": "look around"}
    )
    assert response.status_code == 422
    assert "key" in response.json()["detail"].lower()
    campaign = await db_session.get(Campaign, uuid.UUID(campaign_id), populate_existing=True)
    assert campaign is not None
    assert campaign.turn_number == 0
