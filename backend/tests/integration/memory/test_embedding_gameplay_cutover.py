"""Real memory publication racing an embedding cutover."""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.memory import embedding_worker
from app.memory.embedding_lifecycle import ensure_campaign_embedding_index
from app.memory.job_publication import JobOutput, publish_job
from app.models.embedding_index import EmbeddingIndex, EmbeddingRebuildState
from app.models.memory_fact import MemoryFact
from app.models.source_embedding import EmbeddingWorkState, SourceEmbedding
from tests.integration.memory.embedding_support import install_provider
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_job_publication import _claimed_job


async def test_real_publication_during_cutover_is_caught_up_before_activation(
    history_fixture: HistoryFixture, monkeypatch
) -> None:
    install_provider(monkeypatch)
    f = history_fixture
    await ensure_campaign_embedding_index(
        f.session, user_id=f.campaign.user_id, campaign_id=f.campaign.id
    )

    entered = asyncio.Event()
    release = asyncio.Event()
    original_cutover = embedding_worker.cutover

    async def parked_cutover(db, claim, cfg):
        entered.set()
        await release.wait()
        return await original_cutover(db, claim, cfg)

    monkeypatch.setattr(embedding_worker, "cutover", parked_cutover)
    work = asyncio.create_task(embedding_worker.process_campaign_once(f.campaign.id))
    await asyncio.wait_for(entered.wait(), timeout=10)

    _job, claim, generations, item, _state = await _claimed_job(f)
    fact_payload = {
        "content": "Rook opened the gate.",
        "category": "event",
        "assertion_type": "occurrence",
        "entities": [{"name": "Rook", "type": "npc", "role": "actor"}],
        "attribution": [],
        "source_turns": ["t1"],
        "temporal_references": [],
        "importance": {"level": "ordinary", "reason": "A witnessed event."},
    }
    assert await publish_job(
        f.session,
        claim,
        (
            JobOutput(generations[0].id, '{"text":"Rook opened the gate."}'),
            JobOutput(generations[1].id, json.dumps({"facts": [fact_payload]})),
        ),
    )
    await f.session.commit()

    target = await f.session.scalar(
        select(EmbeddingIndex).where(
            EmbeddingIndex.campaign_id == f.campaign.id,
            EmbeddingIndex.rebuild_state == EmbeddingRebuildState.RUNNING,
        )
    )
    assert target is not None
    release.set()
    await work

    await f.session.refresh(target)
    assert target.is_active is False
    assert target.rebuild_state is EmbeddingRebuildState.RUNNING

    monkeypatch.setattr(embedding_worker, "cutover", original_cutover)
    await embedding_worker.process_campaign_once(f.campaign.id)
    fact = await f.session.scalar(select(MemoryFact).where(MemoryFact.batch_id == item.id))
    assert fact is not None
    row = await f.session.scalar(
        select(SourceEmbedding).where(
            SourceEmbedding.index_id == target.id,
            SourceEmbedding.memory_fact_id == fact.id,
        )
    )
    assert row is not None and row.work_state is EmbeddingWorkState.EMBEDDED
    await f.session.refresh(target)
    assert target.is_active is True
