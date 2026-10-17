import uuid
from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.ai.generation_context import generation_context
from app.ai.npc_director import invoke_single_npc
from app.dependencies import get_db_context
from app.memory.compressor import ensure_compression
from app.memory.fact_extractor import extract_and_store_facts
from app.memory.global_summary import update_global_summary
from app.models.campaign import Campaign
from app.models.memory_fact import MemoryFact
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


async def test_memory_and_npc_jobs_use_the_owner_without_holding_database_connections(
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
            Turn(
                campaign_id=campaign_id,
                turn_number=1,
                player_action="look",
                narration="The inn is closed.",
                model_used="jobs-model",
            )
        )
        await db.commit()

    async def embedding(text: str) -> list[float]:
        assert_no_db_held()
        return [0.1] * 384

    with generation_context(owner):
        async with get_db_context() as db:
            await ensure_compression(str(campaign_id), 20, db)
            await db.commit()
        async with get_db_context() as db:
            result = await update_global_summary(campaign_id, 1, db)
            await db.commit()
        with patch(
            "app.memory.fact_extractor.generate_embedding", new=AsyncMock(side_effect=embedding)
        ):
            await extract_and_store_facts(campaign_id, 1, "look", "The inn is closed.")
        dialogue = await invoke_single_npc("Innkeeper", {"name": "Innkeeper"}, "hello", "An inn.")

    assert result == "The inn is closed."
    assert dialogue.dialogue == "Welcome!"
    provider = generation_clients["jobs-key"][0]
    assert provider.generate.await_count == 4
    for call in provider.generate.call_args_list:
        assert call.kwargs["model"] == "jobs-model"
        assert call.kwargs["max_tokens"] == 60000
    async with get_db_context() as db:
        turn = (await db.execute(select(Turn).where(Turn.campaign_id == campaign_id))).scalar_one()
        campaign = await db.get(Campaign, campaign_id)
        facts = (
            (await db.execute(select(MemoryFact).where(MemoryFact.campaign_id == campaign_id)))
            .scalars()
            .all()
        )
        assert turn.summary == "[Turn 1] The inn is closed."
        assert campaign is not None
        assert campaign.global_summary == "The inn is closed."
        assert len(facts) == 1
        assert facts[0].content == "The inn is closed."
