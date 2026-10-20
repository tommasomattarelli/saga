import uuid
from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from app.ai.generation_context import generation_context
from app.ai.npc_director import invoke_single_npc
from app.dependencies import get_db_context
from app.memory.compressor import ensure_compression
from app.memory.fact_extractor import extract_and_store_facts
from app.memory.global_summary import update_global_summary
from app.models.campaign import Campaign
from app.models.embedding_index import EmbeddingIndex, EmbeddingRebuildState
from app.models.memory_fact import MemoryFact
from app.models.source_embedding import EmbeddingWorkState, SourceEmbedding
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


async def test_compression_batches_never_call_llm_with_database_checked_out(
    auth_client: AsyncClient,
    assert_no_db_held: Callable[[], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import patch

    response = await auth_client.post(
        "/api/campaigns",
        json={"world_id": "the-awakening", "name": "Batch Compression", "difficulty": "medium"},
    )
    campaign_id = uuid.UUID(response.json()["id"])
    async with get_db_context() as db:
        db.add(
            EmbeddingIndex(
                campaign_id=campaign_id,
                provider="openrouter",
                model="test-embed-model",
                endpoint_identity="https://openrouter.ai/api/v1",
                pipeline_version="embed-v1",
                dimension=1536,
                is_active=True,
                rebuild_state=EmbeddingRebuildState.COMPLETED,
            )
        )
        db.add_all(
            [
                Turn(
                    campaign_id=campaign_id,
                    turn_number=turn_number,
                    player_action="explore",
                    narration=f"Turn {turn_number}",
                    model_used="test",
                )
                for turn_number in range(1, 7)
            ]
        )
        await db.commit()

    monkeypatch.setattr(
        "app.memory.compressor.get_gameplay_config",
        lambda: SimpleNamespace(context_window_turns=1, compression_enabled=True),
    )

    calls = 0

    async def compress(_turns):
        nonlocal calls
        calls += 1
        assert_no_db_held()
        return "A batch summary." if calls == 1 else None

    with patch("app.memory.compressor.compress_turns_batch_with_retry", new=compress):
        async with get_db_context() as db:
            await ensure_compression(str(campaign_id), 10, db)
            await db.commit()
    assert calls == 2


async def test_compressor_loser_does_not_enqueue_over_concurrent_winner(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace
    from unittest.mock import patch

    from app.memory.embedding_queue import enqueue_source_embedding
    from app.models.embedding_index import text_hash
    from app.models.source_embedding import EmbeddingSourceType

    campaign_response = await auth_client.post(
        "/api/campaigns",
        json={"world_id": "the-awakening", "name": "Compression Race", "difficulty": "medium"},
    )
    campaign_id = uuid.UUID(campaign_response.json()["id"])
    async with get_db_context() as db:
        index = EmbeddingIndex(
            campaign_id=campaign_id,
            provider="openrouter",
            model="test-embed-model",
            endpoint_identity="https://openrouter.ai/api/v1",
            pipeline_version="embed-v1",
            dimension=1536,
            is_active=True,
            rebuild_state=EmbeddingRebuildState.COMPLETED,
        )
        turn = Turn(
            campaign_id=campaign_id,
            turn_number=1,
            player_action="explore",
            narration="A rival arrives.",
            model_used="test",
        )
        db.add_all([index, turn])
        await db.commit()
        turn_id = turn.id
    monkeypatch.setattr(
        "app.memory.compressor.get_gameplay_config",
        lambda: SimpleNamespace(context_window_turns=1, compression_enabled=True),
    )

    async def competing_compressor(_turns):
        async with get_db_context() as winner_db:
            await winner_db.execute(
                text("SELECT id FROM campaigns WHERE id = :cid FOR UPDATE"),
                {"cid": campaign_id},
            )
            await winner_db.execute(
                text("UPDATE turns SET summary = :summary WHERE id = :tid"),
                {"summary": "Concurrent winner summary", "tid": turn_id},
            )
            await enqueue_source_embedding(
                winner_db,
                campaign_id=campaign_id,
                source_type=EmbeddingSourceType.TURN,
                source_id=turn_id,
                source_text="Concurrent winner summary",
            )
            await winner_db.commit()
        return "Losing summary"

    with patch("app.memory.compressor.compress_turns_batch_with_retry", new=competing_compressor):
        async with get_db_context() as db:
            await ensure_compression(str(campaign_id), 10, db)
            await db.commit()

    async with get_db_context() as db:
        persisted = await db.get(Turn, turn_id)
        sources = (
            (await db.execute(select(SourceEmbedding).where(SourceEmbedding.turn_id == turn_id)))
            .scalars()
            .all()
        )
    assert persisted is not None
    assert persisted.summary == "Concurrent winner summary"
    assert len(sources) == 1
    assert sources[0].text_hash == text_hash("Concurrent winner summary")


async def test_fact_writer_rollback_removes_source_and_queued_embedding(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    campaign_response = await auth_client.post(
        "/api/campaigns",
        json={"world_id": "the-awakening", "name": "Fact Rollback", "difficulty": "medium"},
    )
    campaign_id = uuid.UUID(campaign_response.json()["id"])
    async with get_db_context() as db:
        db.add(
            EmbeddingIndex(
                campaign_id=campaign_id,
                provider="openrouter",
                model="test-embed-model",
                endpoint_identity="https://openrouter.ai/api/v1",
                pipeline_version="embed-v1",
                dimension=1536,
                is_active=True,
                rebuild_state=EmbeddingRebuildState.COMPLETED,
            )
        )
        await db.commit()
    monkeypatch.setattr(
        "app.memory.fact_extractor.get_gameplay_config",
        lambda: SimpleNamespace(fact_extraction_enabled=True),
    )
    monkeypatch.setattr(
        "app.memory.fact_extractor.extract_facts",
        AsyncMock(
            return_value=[
                {"entity_name": "Guard", "entity_type": "npc", "content": "The guard fled."}
            ]
        ),
    )

    def fail_commit(_session: Session) -> None:
        raise RuntimeError("simulated commit failure")

    event.listen(Session, "before_commit", fail_commit)
    try:
        with patch("app.memory.embedding_worker.wake_embedding_worker") as wake:
            await extract_and_store_facts(campaign_id, 1, "look", "The guard fled.")
            wake.assert_not_called()
    finally:
        event.remove(Session, "before_commit", fail_commit)

    async with get_db_context() as db:
        assert (
            await db.scalar(select(MemoryFact.id).where(MemoryFact.campaign_id == campaign_id))
            is None
        )
        assert (
            await db.scalar(
                select(SourceEmbedding.id).where(SourceEmbedding.campaign_id == campaign_id)
            )
            is None
        )


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
        async with get_db_context() as db:
            await ensure_compression(str(campaign_id), 20, db)
            await db.commit()
        async with get_db_context() as db:
            result = await update_global_summary(campaign_id, 1, db)
            await db.commit()
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
        sources = (
            (
                await db.execute(
                    select(SourceEmbedding).where(SourceEmbedding.campaign_id == campaign_id)
                )
            )
            .scalars()
            .all()
        )
        assert {source.turn_id for source in sources if source.turn_id} == {turn.id}
        assert {source.memory_fact_id for source in sources if source.memory_fact_id} == {
            facts[0].id
        }
        assert all(source.work_state == EmbeddingWorkState.PENDING for source in sources)
