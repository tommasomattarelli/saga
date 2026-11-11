import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Callable

import httpx
import openai
import pytest
from httpx import AsyncClient

from app.ai.generation_context import generation_context
from app.ai.providers import base
from app.ai.providers.local import LocalProvider
from app.ai.router import get_generation, get_user_generation
from app.memory.batch_source_contracts import BatchInput
from app.memory.producer_prompts import prepare_request
from app.memory.producers import generate_memory
from app.memory.production_policy import FactsPolicy
from app.security.auth import decode_token
from tests.action_support import action_body


@pytest.fixture
async def affinity_client(
    monkeypatch: pytest.MonkeyPatch, assert_no_db_held: Callable[[], None]
) -> AsyncIterator[tuple[LocalProvider, list[httpx.Request]]]:
    requests: list[httpx.Request] = []

    async def complete(request: httpx.Request) -> httpx.Response:
        assert_no_db_held()
        requests.append(request)
        body = json.loads(request.content)
        message: dict[str, object] = {
            "role": "assistant",
            "content": json.dumps(
                {
                    "status": "speaking",
                    "lines": ["Welcome!"],
                    "facts": [],
                    "summary": "The square is quiet.",
                }
            ),
        }
        if "response_format" in body:
            message["content"] = '{"facts":[]}'
        if "tools" in body:
            if body["messages"][-1]["role"] == "user":
                message = {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "ask",
                            "type": "function",
                            "function": {
                                "name": "invoke_npc",
                                "arguments": json.dumps({"name": "Lyra", "context": "Say hello."}),
                            },
                        }
                    ],
                }
            else:
                message = {"role": "assistant", "content": "[[npc:Lyra:1]] The clearing is quiet."}
        return httpx.Response(
            200,
            json={
                "id": f"gen-{len(requests)}",
                "object": "chat.completion",
                "created": 0,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls" if "tool_calls" in message else "stop",
                        "message": message,
                    }
                ],
            },
        )

    provider = LocalProvider("https://openrouter.ai/api/v1", "shared-key")
    await provider.client.close()
    provider.client = openai.AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key="shared-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(complete)),
        default_headers={"X-App": "preserved"},
        max_retries=2,
    )
    monkeypatch.setattr(base, "_providers", {("openrouter", "shared-key", None): provider})
    try:
        yield provider, requests
    finally:
        await provider.client.close()


async def configure(client: AsyncClient) -> tuple[uuid.UUID, list[str]]:
    assert (
        await client.put("/api/settings/api-keys", json={"openrouter": "shared-key"})
    ).status_code == 200
    assert (
        await client.patch(
            "/api/settings",
            json={
                "generation_provider": "openrouter",
                "generation_model": "affinity-model",
            },
        )
    ).status_code == 200
    campaigns: list[str] = []
    for index in range(2):
        response = await client.post(
            "/api/campaigns",
            json={
                "world_id": "the-awakening",
                "name": f"Affinity {index}",
                "difficulty": "medium",
            },
        )
        assert response.status_code == 201
        campaigns.append(response.json()["id"])
    token = client.headers["Authorization"].removeprefix("Bearer ")
    return uuid.UUID(str(decode_token(token)["sub"])), campaigns


async def generate_test_facts(action: str, narration: str) -> None:
    source = BatchInput.model_validate(
        {
            "turns": (
                {
                    "reference": "t1",
                    "turn_id": uuid.uuid4(),
                    "player_action": action,
                    "narration": narration,
                    "operations": None,
                },
            )
        }
    )
    policy = FactsPolicy.model_validate(
        {
            "max_per_batch": 4,
            "importance_levels": [
                {"name": "ordinary", "criteria": "Useful later", "examples": "A clue."}
            ],
        }
    )
    await generate_memory(prepare_request("facts", source, language="en", facts_policy=policy))


async def test_real_concurrent_campaigns_bind_dm_actors_without_client_mutation(
    auth_client: AsyncClient,
    affinity_client: tuple[LocalProvider, list[httpx.Request]],
) -> None:
    provider, requests = affinity_client
    owner, campaigns = await configure(auth_client)
    bodies = [await action_body(auth_client, campaign, "Greet Lyra.") for campaign in campaigns]
    responses = await asyncio.gather(
        *[
            auth_client.post(f"/api/campaigns/{campaign}/action", json=body)
            for campaign, body in zip(campaigns, bodies, strict=True)
        ]
    )
    assert [r.status_code for r in responses] == [200, 200]
    assert {r.headers.get("x-session-id") for r in requests} == set(campaigns)
    for campaign in campaigns:
        bodies = [json.loads(r.content) for r in requests if r.headers["x-session-id"] == campaign]
        assert len([b for b in bodies if "tools" in b]) == 2
        assert len([b for b in bodies if "response_format" in b]) == 1
        assert len([b for b in bodies if "tools" not in b and "response_format" not in b]) == 0
    before = len(requests)
    assert (
        await auth_client.post(
            f"/api/campaigns/{campaigns[0]}/action",
            json=await action_body(auth_client, campaigns[0], "Greet again."),
        )
    ).status_code == 200
    assert {r.headers["x-session-id"] for r in requests[before:]} == {campaigns[0]}
    assert all(r.headers["x-app"] == "preserved" for r in requests)
    assert "x-session-id" not in provider.client.default_headers
    assert provider.client.max_retries == 2
    unscoped, _ = await get_user_generation(owner)
    assert unscoped is provider


async def test_campaign_scope_survives_owner_rebinding_and_background_request_exit(
    auth_client: AsyncClient,
    affinity_client: tuple[LocalProvider, list[httpx.Request]],
) -> None:
    from app.ai.session_affinity import campaign_session

    provider, requests = affinity_client
    owner, campaigns = await configure(auth_client)
    ready = asyncio.Event()

    async def later() -> None:
        await ready.wait()
        with generation_context(owner):
            await generate_test_facts("look", "The inn is closed.")

    with campaign_session(uuid.UUID(campaigns[0])), generation_context(owner):
        task = asyncio.create_task(later())
    with campaign_session(uuid.UUID(campaigns[1])), generation_context(owner):
        ready.set()
        await task
        await generate_test_facts("look", "The square is quiet.")
    assert [r.headers["x-session-id"] for r in requests] == campaigns
    with generation_context(owner):
        unscoped, _ = await get_generation()
        assert unscoped is provider


async def test_unauthorized_campaign_emits_no_provider_request(
    auth_client: AsyncClient,
    affinity_client: tuple[LocalProvider, list[httpx.Request]],
) -> None:
    _, requests = affinity_client
    await configure(auth_client)
    response = await auth_client.post(
        f"/api/campaigns/{uuid.uuid4()}/action",
        json={
            "action": "look",
            "request_id": str(uuid.uuid4()),
            "expected_head_turn_id": None,
            "expected_context_epoch": 0,
        },
    )
    assert response.status_code == 404
    assert requests == []


async def test_config_can_disable_campaign_affinity_without_mutating_shared_client(
    auth_client: AsyncClient,
    affinity_client: tuple[LocalProvider, list[httpx.Request]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from copy import deepcopy

    from app.ai import router
    from app.ai.session_affinity import campaign_session

    provider, requests = affinity_client
    owner, campaigns = await configure(auth_client)
    config = deepcopy(router._load_config())
    config["generation"]["openrouter_session_affinity"] = False
    monkeypatch.setattr(router, "_load_config", lambda: config)
    with campaign_session(uuid.UUID(campaigns[0])), generation_context(owner):
        resolved, _ = await get_generation()
        assert resolved is provider
        await generate_test_facts("look", "The square is quiet.")
    assert len(requests) == 1
    assert "x-session-id" not in requests[0].headers


@pytest.mark.parametrize("provider_name", ["openai", "google", "local"])
async def test_non_openrouter_generation_never_receives_campaign_header(
    auth_client: AsyncClient,
    affinity_client: tuple[LocalProvider, list[httpx.Request]],
    provider_name: str,
) -> None:
    from app.ai.session_affinity import campaign_session

    provider, requests = affinity_client
    owner, campaigns = await configure(auth_client)
    if provider_name != "local":
        assert (
            await auth_client.put("/api/settings/api-keys", json={provider_name: "shared-key"})
        ).status_code == 200
    base._providers[
        (
            provider_name,
            None if provider_name == "local" else "shared-key",
            "http://localhost:11434/v1" if provider_name == "local" else None,
        )
    ] = provider
    assert (
        await auth_client.patch(
            "/api/settings",
            json={
                "generation_provider": provider_name,
                "generation_model": "other-model",
                "generation_local_endpoint": "ollama" if provider_name == "local" else None,
            },
        )
    ).status_code == 200
    with campaign_session(uuid.UUID(campaigns[0])), generation_context(owner):
        resolved, _ = await get_generation()
        assert resolved is provider
        await generate_test_facts("look", "The square is quiet.")
    assert len(requests) == 1
    assert "x-session-id" not in requests[0].headers
