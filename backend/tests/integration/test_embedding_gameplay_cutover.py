"""Real-writer races against the embedding index cutover."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app import dependencies
from app.memory import embedding_worker
from app.memory.compressor import ensure_compression
from app.memory.embedding_lifecycle import ensure_campaign_embedding_index
from app.memory.fact_extractor import extract_and_store_facts
from app.models.embedding_index import EmbeddingIndex, EmbeddingRebuildState, text_hash
from app.models.memory_fact import MemoryFact
from app.models.source_embedding import EmbeddingWorkState, SourceEmbedding
from tests.integration.embedding_support import (
    add_turn,
    create_user_campaign,
    install_provider,
)


async def test_real_writers_during_cutover_are_caught_up_before_activation(
    db_session, monkeypatch
) -> None:
    install_provider(monkeypatch)
    user, campaign = await create_user_campaign(db_session)
    turn = await add_turn(db_session, campaign, 5, None)
    await db_session.commit()
    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)

    entered = asyncio.Event()
    release = asyncio.Event()
    original_cutover = embedding_worker.cutover

    async def parked_cutover(db, claim, cfg):
        entered.set()
        await release.wait()
        return await original_cutover(db, claim, cfg)

    monkeypatch.setattr(embedding_worker, "cutover", parked_cutover)
    work = asyncio.create_task(embedding_worker.process_campaign_once(campaign.id))
    await asyncio.wait_for(entered.wait(), timeout=10)

    async def fake_extract(*args, **kwargs):
        return [{"entity_name": "Rook", "entity_type": "npc", "content": "Rook opened the gate."}]

    monkeypatch.setattr("app.memory.fact_extractor.extract_facts", fake_extract)
    await extract_and_store_facts(campaign.id, 5, "open gate", "Rook opened it.")

    monkeypatch.setattr(
        "app.memory.compressor.get_gameplay_config",
        lambda: type(
            "Config",
            (),
            {
                "context_window_turns": 2,
                "compression_enabled": False,
            },
        )(),
    )
    await ensure_compression(str(campaign.id), 10, db_session)
    await db_session.commit()

    indexes = list(
        (
            await db_session.execute(
                select(EmbeddingIndex).where(EmbeddingIndex.campaign_id == campaign.id)
            )
        ).scalars()
    )
    target = next(index for index in indexes if not index.is_active)
    release.set()
    await work

    await db_session.refresh(target)
    assert target.is_active is False
    assert target.rebuild_state in (EmbeddingRebuildState.QUEUED, EmbeddingRebuildState.RUNNING)

    monkeypatch.setattr(embedding_worker, "cutover", original_cutover)
    await embedding_worker.process_campaign_once(campaign.id)
    active = (
        await db_session.execute(
            select(EmbeddingIndex).where(
                EmbeddingIndex.campaign_id == campaign.id, EmbeddingIndex.is_active.is_(True)
            )
        )
    ).scalar_one()
    assert active.id == target.id

    fact = (
        await db_session.execute(select(MemoryFact).where(MemoryFact.campaign_id == campaign.id))
    ).scalar_one()
    active_id = active.id
    fact_id = fact.id
    fact_content = fact.content
    turn_id = turn.id
    db_session.expire_all()
    stored_turn = await db_session.get(type(turn), turn_id)
    assert stored_turn is not None and stored_turn.summary is not None
    rows = list(
        (
            await db_session.execute(
                select(SourceEmbedding).where(SourceEmbedding.index_id == active_id)
            )
        ).scalars()
    )
    by_source = {row.memory_fact_id: row for row in rows if row.memory_fact_id}
    turn_row = next(row for row in rows if row.turn_id == turn.id)
    assert turn_row.work_state is EmbeddingWorkState.EMBEDDED
    assert turn_row.text_hash == text_hash(stored_turn.summary)
    assert by_source[fact_id].work_state is EmbeddingWorkState.EMBEDDED
    assert by_source[fact_id].text_hash == text_hash(fact_content)


async def test_source_written_after_the_switch_queues_on_the_new_active_index(
    db_session, monkeypatch, assert_no_db_held
) -> None:
    async def embed(texts, resolved):
        assert_no_db_held()
        return SimpleNamespace(vectors=[[1.0] * 8 for _ in texts], dimension=8)

    install_provider(monkeypatch, embed=embed)
    user, campaign = await create_user_campaign(db_session)
    await add_turn(db_session, campaign, 1, "A quiet road.")
    await db_session.commit()
    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)
    await db_session.commit()
    await embedding_worker.process_campaign_once(campaign.id)

    active = (
        await db_session.execute(
            select(EmbeddingIndex).where(
                EmbeddingIndex.campaign_id == campaign.id, EmbeddingIndex.is_active.is_(True)
            )
        )
    ).scalar_one()
    active_id = active.id

    async def fake_extract(*args, **kwargs):
        return [{"entity_name": "Rook", "entity_type": "npc", "content": "Rook holds the gate."}]

    monkeypatch.setattr("app.memory.fact_extractor.extract_facts", fake_extract)
    await extract_and_store_facts(campaign.id, 2, "hold the gate", "Rook holds it.")

    rows = list(
        (
            await db_session.execute(
                select(SourceEmbedding).where(SourceEmbedding.index_id == active_id)
            )
        ).scalars()
    )
    fact_rows = [row for row in rows if row.memory_fact_id]
    assert len(fact_rows) == 1
    assert fact_rows[0].work_state is EmbeddingWorkState.PENDING


async def test_compressor_rolls_back_summary_when_queue_write_fails(
    db_session, monkeypatch
) -> None:
    from app.memory import embedding_queue

    _, campaign = await create_user_campaign(db_session)
    turn = await add_turn(db_session, campaign, 1, None)
    await db_session.commit()
    monkeypatch.setattr(
        "app.memory.compressor.get_gameplay_config",
        lambda: type("Config", (), {"context_window_turns": 2, "compression_enabled": False})(),
    )

    async def fail_enqueue(*args, **kwargs):
        raise RuntimeError("queue write failed")

    monkeypatch.setattr(embedding_queue, "enqueue_source_embedding", fail_enqueue)
    with pytest.raises(RuntimeError, match="queue write failed"):
        await ensure_compression(str(campaign.id), 10, db_session)
    await db_session.rollback()
    async with dependencies.async_session() as verify_db:
        stored = await verify_db.get(type(turn), turn.id)
        assert stored is not None and stored.summary is None
        assert (
            await verify_db.execute(
                select(SourceEmbedding).where(SourceEmbedding.campaign_id == campaign.id)
            )
        ).scalars().all() == []
