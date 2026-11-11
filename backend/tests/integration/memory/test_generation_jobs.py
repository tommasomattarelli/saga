import uuid
from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.ai.generation_context import generation_context
from app.ai.npc_director import invoke_single_npc
from app.dependencies import get_db_context
from app.models.campaign import Campaign
from app.models.embedding_index import EmbeddingIndex, EmbeddingRebuildState
from app.models.turn import Turn
from app.security.auth import decode_token


async def test_connection_probe_detects_an_open_transaction(
    assert_no_db_held: Callable[[], None],
) -> None:
    async with get_db_context() as db:
        await db.execute(text("SELECT 1"))
        with pytest.raises(AssertionError, match="spans a provider call"):
            assert_no_db_held()
    assert_no_db_held()


async def test_npc_job_uses_owner_without_holding_database_connection(
    auth_client: AsyncClient,
    generation_clients: dict[str, list[AsyncMock]],
    assert_no_db_held: Callable[[], None],
) -> None:
    await auth_client.put("/api/settings/api-keys", json={"openai": "jobs-key"})
    await auth_client.patch(
        "/api/settings", json={"generation_provider": "openai", "generation_model": "jobs-model"}
    )
    response = await auth_client.post(
        "/api/campaigns",
        json={"world_id": "the-awakening", "name": "Jobs", "difficulty": "medium"},
    )
    assert response.status_code == 201
    campaign_id = uuid.UUID(response.json()["id"])
    token = auth_client.headers["Authorization"].removeprefix("Bearer ")
    owner = uuid.UUID(str(decode_token(token)["sub"]))
    async with get_db_context() as db:
        db.add(
            EmbeddingIndex(
                campaign_id=campaign_id,
                provider="openrouter",
                model="test-embed-model",
                pipeline_version="embed-v1",
                dimension=1536,
                is_active=True,
                rebuild_state=EmbeddingRebuildState.COMPLETED,
            )
        )
        db.add(
            Turn(
                campaign_id=campaign_id,
                turn_number=1,
                player_action="look",
                narration="The inn is closed.",
                model_used="jobs-model",
            )
        )
        await db.commit()

    with generation_context(owner):
        dialogue = await invoke_single_npc("Innkeeper", {"name": "Innkeeper"}, "hello", "An inn.")

    assert dialogue.lines == ("Welcome!",)
    assert set(generation_clients) == {"jobs-key"}
    provider = generation_clients["jobs-key"][0]
    provider.generate.assert_awaited_once()
    assert provider.generate.call_args.kwargs["model"] == "jobs-model"
    assert provider.generate.call_args.kwargs["max_tokens"] == 60000
    assert_no_db_held()
    async with get_db_context() as db:
        assert await db.get(Campaign, campaign_id) is not None
