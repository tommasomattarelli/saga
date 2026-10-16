import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.security.auth import decode_token


async def test_settings_do_not_advertise_direct_anthropic(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/settings")

    assert response.status_code == 200
    assert "has_anthropic_key" not in response.json()


async def test_retired_provider_rejects_key_updates_without_deleting_legacy_keys(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    token = auth_client.headers["Authorization"].removeprefix("Bearer ")
    user_id = uuid.UUID(str(decode_token(token)["sub"]))
    user = await db_session.get(User, user_id)
    assert user is not None
    user.anthropic_api_key_enc = "legacy-anthropic-ciphertext"
    user.openai_api_key_enc = "existing-openai-ciphertext"
    await db_session.commit()

    response = await auth_client.put(
        "/api/settings/api-keys",
        json={"anthropic": "new-key", "openai": "must-not-be-written"},
    )

    assert response.status_code == 400
    assert "OpenRouter" in response.json()["detail"]
    await db_session.refresh(user)
    assert user.anthropic_api_key_enc == "legacy-anthropic-ciphertext"
    assert user.openai_api_key_enc == "existing-openai-ciphertext"
