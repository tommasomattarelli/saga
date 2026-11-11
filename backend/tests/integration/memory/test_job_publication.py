import json
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.memory.batch_input import load_batch_input
from app.memory.batch_source_contracts import BatchInput, BatchTurnSource
from app.memory.job_claims import JobClaim, claim_job
from app.memory.job_publication import JobOutput, publish_job
from app.memory.job_requests import build_job_manifest, job_manifest_hash
from app.memory.producer_prompts import PRODUCER_VERSION
from app.models.embedding_index import EmbeddingIndex, EmbeddingRebuildState
from app.models.memory_batch import MemoryBatch, MemoryBatchTurn
from app.models.memory_document import MemoryState, MemorySummary
from app.models.memory_fact import MemoryFact, MemoryFactSource
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob
from app.models.source_embedding import SourceEmbedding
from tests.integration.memory.storage_support import HistoryFixture


async def _claimed_job(
    f: HistoryFixture,
) -> tuple[MemoryJob, JobClaim, tuple[MemoryGeneration, ...], MemoryBatch, MemoryState]:
    first = await f.turn()
    second = await f.turn(first)
    source = BatchInput(
        turns=tuple(
            BatchTurnSource(
                reference=f"t{index}",
                turn_id=turn.id,
                player_action=turn.player_action,
                narration=turn.narration,
                operations=None,
            )
            for index, turn in enumerate((first, second), start=1)
        )
    )
    item = MemoryBatch(
        id=uuid4(),
        campaign_id=f.campaign.id,
        policy_id=f.policy.id,
        previous_batch_id=None,
        source_head_turn_id=second.id,
        manifest_hash=source.source_hash(),
    )
    f.session.add(item)
    await f.session.flush()
    f.session.add_all(
        MemoryBatchTurn(
            campaign_id=f.campaign.id, batch_id=item.id, ordinal=index, turn_id=turn.id
        )
        for index, turn in enumerate((first, second), start=1)
    )
    state = MemoryState(
        id=uuid4(), campaign_id=f.campaign.id, policy_id=f.policy.id, context_epoch=0
    )
    f.session.add(state)
    await f.session.commit()
    turns = [first, second]
    f.campaign.active_head_turn_id = turns[-1].id
    f.campaign.active_memory_state_id = state.id
    source = await load_batch_input(f.session, f.campaign.id, item.id)
    manifest = build_job_manifest(
        "batch", source, language="en", facts_policy=f.policy.payload.facts
    )
    job = MemoryJob(
        id=uuid4(),
        campaign_id=f.campaign.id,
        policy_id=f.policy.id,
        batch_id=item.id,
        memory_state_id=state.id,
        context_epoch=0,
        kind="batch",
        logical_key="1" * 64,
        manifest=manifest,
        manifest_hash=job_manifest_hash(manifest),
        producer_version=PRODUCER_VERSION,
        prompt_version=manifest.instruction_version,
        state="queued",
        attempt_count=0,
        retry_cycle=0,
        cycle_attempt_count=0,
        activation_state="pending",
    )
    f.session.add(job)
    await f.session.commit()
    claim = await claim_job(f.session, f.campaign.id, job.id)
    assert claim is not None
    generations = tuple(
        MemoryGeneration(
            id=uuid4(),
            job_id=job.id,
            attempt_id=claim.attempt_id,
            campaign_id=job.campaign_id,
            policy_id=job.policy_id,
            batch_id=job.batch_id,
            role=role,
            provider="test",
            model="test",
        )
        for role in ("summary", "facts")
    )
    f.session.add_all(generations)
    await f.session.commit()
    return job, claim, generations, item, state


async def test_complete_batch_with_empty_facts_publishes_atomically(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    job, claim, generations, item, state = await _claimed_job(f)
    outputs = (
        JobOutput(generations[0].id, json.dumps({"text": "An immutable summary."})),
        JobOutput(generations[1].id, '{"facts":[]}'),
    )
    assert await publish_job(f.session, claim, outputs)
    await f.session.commit()
    summary = await f.session.scalar(
        select(MemorySummary).where(MemorySummary.batch_id == item.id)
    )
    assert summary is not None
    assert state.last_compacted_batch_id is None
    assert job.state == "succeeded"
    assert job.activation_state == "detached"
    assert (
        await f.session.scalar(select(MemoryFact.id).where(MemoryFact.batch_id == item.id)) is None
    )


async def test_malformed_facts_do_not_publish_half_batch(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    job, claim, generations, item, state = await _claimed_job(f)
    batch_id, job_id = item.id, job.id
    invalid = '{"facts":[{"content":"bad","category":"nope"}]}'
    with pytest.raises(ValueError):
        await publish_job(
            f.session,
            claim,
            (
                JobOutput(generations[0].id, '{"text":"summary"}'),
                JobOutput(generations[1].id, invalid),
            ),
        )
    await f.session.rollback()
    assert (
        await f.session.scalar(select(MemorySummary.id).where(MemorySummary.batch_id == batch_id))
        is None
    )
    persisted_job = await f.session.get(MemoryJob, job_id)
    assert persisted_job is not None
    assert persisted_job.state == "running"


async def test_stale_claim_does_not_publish(history_fixture: HistoryFixture) -> None:
    f = history_fixture
    job, claim, generations, item, _state = await _claimed_job(f)
    batch_id = item.id
    await f.session.execute(
        text(
            "UPDATE memory_jobs SET lease_expires_at = clock_timestamp() - interval '1 second' WHERE id = :id"
        ),
        {"id": job.id},
    )
    assert not await publish_job(
        f.session,
        claim,
        (
            JobOutput(generations[0].id, '{"text":"summary"}'),
            JobOutput(generations[1].id, '{"facts":[]}'),
        ),
    )
    await f.session.rollback()
    assert (
        await f.session.scalar(select(MemorySummary.id).where(MemorySummary.batch_id == batch_id))
        is None
    )


async def test_outer_rollback_removes_published_documents(history_fixture: HistoryFixture) -> None:
    f = history_fixture
    job, claim, generations, item, _state = await _claimed_job(f)
    batch_id, job_id = item.id, job.id
    assert await publish_job(
        f.session,
        claim,
        (
            JobOutput(generations[0].id, '{"text":"summary"}'),
            JobOutput(generations[1].id, '{"facts":[]}'),
        ),
    )
    await f.session.rollback()
    assert (
        await f.session.scalar(select(MemorySummary.id).where(MemorySummary.batch_id == batch_id))
        is None
    )
    persisted_job = await f.session.get(MemoryJob, job_id)
    assert persisted_job is not None
    assert persisted_job.state == "running"


async def test_epoch_change_keeps_result_detached(history_fixture: HistoryFixture) -> None:
    f = history_fixture
    job, claim, generations, item, state = await _claimed_job(f)
    newer_state = MemoryState(
        id=uuid4(), campaign_id=f.campaign.id, policy_id=f.policy.id, context_epoch=1
    )
    f.session.add(newer_state)
    f.campaign.context_epoch = 1
    f.campaign.active_memory_state_id = newer_state.id
    await f.session.commit()
    assert await publish_job(
        f.session,
        claim,
        (
            JobOutput(generations[0].id, '{"text":"summary"}'),
            JobOutput(generations[1].id, '{"facts":[]}'),
        ),
    )
    await f.session.commit()
    assert job.activation_state == "detached"
    assert state.last_compacted_batch_id is None
    assert (
        await f.session.scalar(select(MemorySummary.id).where(MemorySummary.batch_id == item.id))
        is not None
    )


@pytest.mark.parametrize("rollback", [False, True])
async def test_fact_source_and_embedding_work_share_publication_transaction(
    history_fixture: HistoryFixture,
    rollback: bool,
) -> None:
    f = history_fixture
    job, claim, generations, item, state = await _claimed_job(f)
    f.session.add(
        EmbeddingIndex(
            campaign_id=f.campaign.id,
            provider="test",
            model="test",
            pipeline_version="test",
            dimension=3,
            is_active=True,
            rebuild_state=EmbeddingRebuildState.COMPLETED,
        )
    )
    await f.session.flush()
    fact = {
        "content": "The guard fled.",
        "category": "event",
        "assertion_type": "occurrence",
        "entities": [{"name": "Guard", "type": "npc", "role": "actor"}],
        "attribution": [],
        "source_turns": ["t1"],
        "temporal_references": [],
        "importance": {"level": "ordinary", "reason": "A witnessed event."},
    }
    await publish_job(
        f.session,
        claim,
        (
            JobOutput(generations[0].id, '{"text":"summary"}'),
            JobOutput(generations[1].id, json.dumps({"facts": [fact]})),
        ),
    )
    if rollback:
        await f.session.rollback()
        assert await f.session.scalar(select(MemorySummary.id)) is None
        assert await f.session.scalar(select(MemoryFact.id)) is None
        assert await f.session.scalar(select(MemoryFactSource.fact_id)) is None
        assert await f.session.scalar(select(SourceEmbedding.id)) is None
        return
    await f.session.commit()
    stored = await f.session.scalar(select(MemoryFact).where(MemoryFact.batch_id == item.id))
    queued = await f.session.scalar(
        select(SourceEmbedding).where(SourceEmbedding.memory_fact_id == stored.id)
    )
    assert stored.ordinal == 1
    assert queued is not None
    assert queued.text_hash
    assert state.last_compacted_batch_id is None
