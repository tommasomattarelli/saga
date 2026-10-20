import asyncio
import uuid
from unittest.mock import AsyncMock

import openai
import pytest
from httpx import ASGITransport, AsyncClient, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.generation_context import generation_context
from app.ai.router import (
    get_generation,
    get_instance_default,
    get_user_generation,
    validate_generation_config,
)
from app.exceptions import ValidationError
from app.main import app
from app.models.user import User
from app.security.auth import create_access_token


async def configure(client: AsyncClient, key: str, model: str) -> str:
    response = await client.put("/api/settings/api-keys", json={"openai": key})
    assert response.status_code == 200
    response = await client.patch(
        "/api/settings", json={"generation_provider": "openai", "generation_model": model}
    )
    assert response.status_code == 200
    response = await client.post(
        "/api/campaigns",
        json={"world_id": "the-awakening", "name": model, "difficulty": "medium"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


async def test_two_real_turns_never_share_clients_or_models(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    generation_clients: dict[str, list[AsyncMock]],
) -> None:
    owner = uuid.uuid4()
    db_session.add(
        User(id=owner, username="second", email="second@test.com", hashed_password="hash")
    )
    await db_session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {create_access_token(owner)}"},
    ) as second:
        first_campaign = await configure(auth_client, "first-key", "first-model")
        second_campaign = await configure(second, "second-key", "second-model")
        responses = await asyncio.gather(
            auth_client.post(
                f"/api/campaigns/{first_campaign}/action", json={"action": "look at the torch"}
            ),
            second.post(
                f"/api/campaigns/{second_campaign}/action",
                json={"action": "listen at the door"},
            ),
        )
        background = [
            task
            for task in asyncio.all_tasks()
            if getattr(task.get_coro(), "__name__", "")
            in {
                "extract_and_store_facts",
                "_background_compression",
                "_background_global_summary",
            }
        ]
        await asyncio.gather(*background)

        assert [response.status_code for response in responses] == [200, 200]
        assert [response.json()["model_used"] for response in responses] == [
            "first-model",
            "second-model",
        ]
        assert set(generation_clients) == {"first-key", "second-key"}
        first = generation_clients["first-key"]
        other = generation_clients["second-key"]
        assert len(first) == len(other) == 1
        assert first[0] is not other[0]
        for providers, model in ((first, "first-model"), (other, "second-model")):
            assert providers[0].generate_with_tools.call_args.kwargs["model"] == model
            assert providers[0].generate.call_args.kwargs["model"] == model
        with pytest.raises(ValidationError, match="context"):
            await get_generation()


@pytest.mark.parametrize("operator", [False, True])
@pytest.mark.parametrize("consent", [False, True])
@pytest.mark.parametrize("personal", [False, True])
async def test_fallback_requires_both_consents_and_an_absent_personal_key(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    generation_clients: dict[str, list[AsyncMock]],
    operator: bool,
    consent: bool,
    personal: bool,
) -> None:
    from app.security.auth import decode_token

    monkeypatch.setattr("app.ai.credentials.settings.openai_api_key", "server-key")
    monkeypatch.setattr("app.ai.credentials.get_server_key_fallback", lambda: {"openai": operator})
    await auth_client.patch(
        "/api/settings", json={"generation_provider": "openai", "generation_model": "chosen-model"}
    )
    await auth_client.put("/api/settings/server-key-consents", json={"openai": consent})
    if personal:
        await auth_client.put("/api/settings/api-keys", json={"openai": "personal-key"})
    payload = (await auth_client.get("/api/settings")).json()
    token = auth_client.headers["Authorization"].removeprefix("Bearer ")
    owner = uuid.UUID(str(decode_token(token)["sub"]))

    if personal or (operator and consent):
        _, config = await get_user_generation(owner)
        expected = "personal-key" if personal else "server-key"
        assert set(generation_clients) == {expected}
        assert payload["credential_source"] == ("personal" if personal else "server")
        assert config.provider == "openai"
        assert config.model == "chosen-model"
    else:
        with pytest.raises(ValidationError, match="key"):
            await get_user_generation(owner)
        assert not generation_clients
        assert payload["credential_source"] == "missing"


@pytest.mark.parametrize(("status_code", "message"), [(401, "key"), (429, "quota")])
async def test_rejected_personal_key_never_retries_on_the_server_key(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    generation_clients: dict[str, list[AsyncMock]],
    status_code: int,
    message: str,
) -> None:
    monkeypatch.setattr("app.ai.credentials.settings.openai_api_key", "server-key")
    monkeypatch.setattr("app.ai.credentials.get_server_key_fallback", lambda: {"openai": True})
    campaign = await configure(auth_client, "rejected-key", "chosen-model")
    await auth_client.put("/api/settings/server-key-consents", json={"openai": True})
    from app.security.auth import decode_token

    token = auth_client.headers["Authorization"].removeprefix("Bearer ")
    await get_user_generation(uuid.UUID(str(decode_token(token)["sub"])))
    generation_clients["rejected-key"][0].generate_with_tools.side_effect = openai.APIStatusError(
        "private-provider-payload",
        response=Response(status_code, request=Request("POST", "https://provider.test/private")),
        body=None,
    )
    response = await auth_client.post(f"/api/campaigns/{campaign}/action", json={"action": "look"})
    assert response.status_code == 502
    assert message in response.json()["detail"]
    assert "private-provider-payload" not in response.text
    assert "rejected-key" not in response.text
    assert set(generation_clients) == {"rejected-key"}
    assert generation_clients["rejected-key"][0].generate_with_tools.await_count == 1


async def test_disabled_provider_is_rechecked_before_a_turn(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    generation_clients: dict[str, list[AsyncMock]],
) -> None:
    campaign = await configure(auth_client, "disabled-key", "chosen-model")
    monkeypatch.setattr("app.ai.credentials.get_allowed_providers", lambda: ["google"])
    response = await auth_client.post(f"/api/campaigns/{campaign}/action", json={"action": "look"})
    assert response.status_code == 422
    assert "not enabled" in response.json()["detail"]
    assert not generation_clients


async def test_legacy_environment_cannot_override_either_profile(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    generation_clients: dict[str, list[AsyncMock]],
) -> None:
    from app.security.auth import decode_token

    default = get_instance_default()
    for key in (
        "SAGA_GLOBAL_PROVIDER",
        "SAGA_GLOBAL_MODEL_HIGH",
        "SAGA_GLOBAL_MODEL_MEDIUM",
        "SAGA_GLOBAL_MODEL_LOW",
        "SAGA_MODEL_DM_NARRATIVE_HIGH_PROVIDER",
        "SAGA_MODEL_MEMORY_COMPRESSION_DEFAULT",
    ):
        monkeypatch.setenv(key, "ignored-legacy-value")
    validate_generation_config()
    assert get_instance_default() == default
    await configure(auth_client, "legacy-proof-key", "personal-model")
    token = auth_client.headers["Authorization"].removeprefix("Bearer ")
    with generation_context(uuid.UUID(str(decode_token(token)["sub"]))):
        _, config = await get_generation()
    assert config.provider == "openai"
    assert config.model == "personal-model"
