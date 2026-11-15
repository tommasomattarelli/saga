import json
from dataclasses import dataclass, replace
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from app.ai.credentials import resolve_generation
from app.memory.batch_input import load_batch_input
from app.memory.batch_source_contracts import BatchInput, BatchTurnSource
from app.memory.job_claims import JobClaim, claim_job
from app.memory.job_identity import build_execution_identity
from app.memory.job_publication import JobOutput, publish_job
from app.memory.job_requests import build_job_manifest, job_manifest_hash, restore_job_requests
from app.memory.producer_contracts import MemoryOutputError
from app.memory.producer_prompts import PRODUCER_VERSION
from app.models.campaign import Campaign, Difficulty
from app.models.embedding_index import EmbeddingIndex, EmbeddingRebuildState
from app.models.history import HistoryContinuation, MemoryPolicy
from app.models.memory_batch import MemoryBatch, MemoryBatchTurn
from app.models.memory_document import MemoryState, MemorySummary
from app.models.memory_fact import MemoryFact, MemoryFactSource
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob, MemoryJobAttempt
from app.models.source_embedding import SourceEmbedding
from app.models.user import User
from tests.integration.memory.job_support import (
    _durable_generation,
    configure_local_generation,
    outputs_for,
    persist_durable_generations,
)
from tests.integration.memory.storage_support import HistoryFixture


async def _claimed_job(
    f: HistoryFixture,
    *,
    raw_by_role: dict[str, str] | None = None,
    status_by_role: dict[str, str] | None = None,
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
    await configure_local_generation(f)
    user = await f.session.get(User, f.campaign.user_id)
    assert user is not None
    config, _, _ = resolve_generation(user)
    identity = build_execution_identity(
        manifest, source, f.policy.payload.facts, config, 3, f.campaign.id
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
        execution_contract_version=1,
        execution_identity=identity,
        execution_identity_hash=identity.digest(1),
        execution_identity_version=1,
    )
    f.session.add(job)
    await f.session.commit()
    claim = await claim_job(f.session, f.campaign.id, job.id)
    assert claim is not None
    attempt = await f.session.get(MemoryJobAttempt, claim.attempt_id)
    assert attempt is not None
    requests = restore_job_requests(manifest, source, f.policy.payload.facts)
    raw_by_role = raw_by_role or {
        "summary": '{"text":"An immutable summary."}',
        "facts": '{"facts":[]}',
    }
    generations = tuple(
        _durable_generation(job, attempt, request, config, raw_by_role[request.kind])
        for request in requests
    )
    for generation in generations:
        generation.status = (status_by_role or {}).get(generation.role, generation.status)
        if generation.status != "valid":
            generation.outcome_reason = "validation_failed"
    await persist_durable_generations(f.session, generations)
    await f.session.commit()
    return job, claim, generations, item, state


async def _foreign_campaign_fixture(f: HistoryFixture) -> HistoryFixture:
    campaign = Campaign(
        id=uuid4(),
        user_id=f.campaign.user_id,
        world_slug="test",
        name="Foreign publication scope",
        difficulty=Difficulty.MEDIUM,
    )
    payload = f.policy.payload
    policy = MemoryPolicy(
        id=uuid4(),
        campaign_id=campaign.id,
        schema_version=1,
        payload=payload,
        payload_hash=payload.policy_hash(),
    )
    root = HistoryContinuation(id=uuid4(), campaign_id=campaign.id)
    f.session.add_all([campaign, policy, root])
    await f.session.flush()
    campaign.memory_policy_id = policy.id
    campaign.active_continuation_id = root.id
    await f.session.commit()
    return HistoryFixture(f.session, campaign, policy, root)


async def test_complete_batch_with_empty_facts_publishes_atomically(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    job, claim, generations, item, state = await _claimed_job(f)
    assert await publish_job(f.session, claim, outputs_for(generations))
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
    invalid = '{"facts":[{"content":"bad","category":"nope"}]}'
    job, claim, generations, item, state = await _claimed_job(
        f, raw_by_role={"summary": '{"text":"summary"}', "facts": invalid}
    )
    batch_id, job_id = item.id, job.id
    with pytest.raises(ValueError):
        await publish_job(f.session, claim, outputs_for(generations))
    await f.session.rollback()
    assert (
        await f.session.scalar(select(MemorySummary.id).where(MemorySummary.batch_id == batch_id))
        is None
    )
    persisted_job = await f.session.get(MemoryJob, job_id)
    assert persisted_job is not None
    assert persisted_job.state == "running"


async def test_mismatched_send_provenance_prevents_any_batch_publication(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    job, claim, generations, item, _state = await _claimed_job(f)
    batch_id, job_id = item.id, job.id
    outputs = outputs_for(generations)
    mismatched = (
        outputs[0],
        JobOutput(outputs[1].role, outputs[1].send_number + 1),
    )

    with pytest.raises(MemoryOutputError, match="receipt is unavailable"):
        await publish_job(f.session, claim, mismatched)
    await f.session.rollback()

    assert (
        await f.session.scalar(select(MemorySummary.id).where(MemorySummary.batch_id == batch_id))
        is None
    )
    assert (
        await f.session.scalar(select(MemoryFact.id).where(MemoryFact.batch_id == batch_id))
        is None
    )
    persisted = await f.session.get(MemoryJob, job_id)
    assert persisted is not None and persisted.state == "running"


@pytest.mark.parametrize("foreign_scope", ["job", "campaign"])
async def test_foreign_claim_scope_cannot_publish_persisted_generations(
    history_fixture: HistoryFixture,
    foreign_scope: str,
) -> None:
    f = history_fixture
    job, claim, generations, item, _state = await _claimed_job(f)
    foreign_fixture = await _foreign_campaign_fixture(f)
    foreign_job, _, foreign_generations, foreign_item, _ = await _claimed_job(
        foreign_fixture,
        raw_by_role={
            "summary": '{"text":"A foreign persisted summary."}',
            "facts": '{"facts":[]}',
        },
    )
    batch_id, job_id = item.id, job.id
    foreign_batch_id = foreign_item.id
    foreign_job_id = foreign_job.id
    foreign_generation_ids = {generation.id for generation in foreign_generations}
    generation_ids = {generation.id for generation in generations}
    foreign_claim = replace(
        claim,
        job_id=foreign_job.id,
        campaign_id=claim.campaign_id if foreign_scope == "job" else foreign_job.campaign_id,
    )

    assert not await publish_job(f.session, foreign_claim, outputs_for(generations))
    await f.session.rollback()
    assert (
        await f.session.scalar(select(MemorySummary.id).where(MemorySummary.batch_id == batch_id))
        is None
    )
    assert (
        await f.session.scalar(select(MemoryFact.id).where(MemoryFact.batch_id == batch_id))
        is None
    )
    assert (
        await f.session.scalar(
            select(MemorySummary.id).where(MemorySummary.batch_id == foreign_batch_id)
        )
        is None
    )
    assert (
        await f.session.scalar(
            select(MemoryFact.id).where(MemoryFact.batch_id == foreign_batch_id)
        )
        is None
    )
    persisted = await f.session.get(MemoryJob, job_id)
    assert persisted is not None and persisted.state == "running"
    foreign_persisted = await f.session.get(MemoryJob, foreign_job_id)
    assert foreign_persisted is not None and foreign_persisted.state == "running"
    assert foreign_generation_ids.isdisjoint(generation_ids)


async def test_persisted_wrong_role_order_cannot_publish(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    job, claim, generations, item, _state = await _claimed_job(f)
    batch_id, job_id = item.id, job.id

    with pytest.raises(MemoryOutputError, match="output roles are incomplete"):
        await publish_job(f.session, claim, tuple(reversed(outputs_for(generations))))
    await f.session.rollback()
    assert (
        await f.session.scalar(select(MemorySummary.id).where(MemorySummary.batch_id == batch_id))
        is None
    )
    assert (
        await f.session.scalar(select(MemoryFact.id).where(MemoryFact.batch_id == batch_id))
        is None
    )
    persisted = await f.session.get(MemoryJob, job_id)
    assert persisted is not None and persisted.state == "running"


async def test_nonvalid_persisted_send_cannot_publish(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    job, claim, generations, item, _state = await _claimed_job(
        f, status_by_role={"facts": "invalid"}
    )
    batch_id, job_id = item.id, job.id

    with pytest.raises(MemoryOutputError, match="persisted valid memory receipt"):
        await publish_job(f.session, claim, outputs_for(generations))
    await f.session.rollback()
    assert (
        await f.session.scalar(select(MemorySummary.id).where(MemorySummary.batch_id == batch_id))
        is None
    )
    assert (
        await f.session.scalar(select(MemoryFact.id).where(MemoryFact.batch_id == batch_id))
        is None
    )
    persisted = await f.session.get(MemoryJob, job_id)
    assert persisted is not None and persisted.state == "running"


async def test_untrusted_raw_override_cannot_replace_persisted_receipt(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    job, claim, generations, item, _state = await _claimed_job(f)
    foreign_fixture = await _foreign_campaign_fixture(f)
    foreign_job, _, foreign_generations, _, _ = await _claimed_job(
        foreign_fixture,
        raw_by_role={
            "summary": '{"text":"A foreign persisted summary."}',
            "facts": '{"facts":[]}',
        },
    )
    foreign_summary = next(
        generation for generation in foreign_generations if generation.role == "summary"
    )

    @dataclass(frozen=True)
    class UntrustedWireEnvelope:
        role: str
        send_number: int
        job_id: UUID
        campaign_id: UUID
        generation_id: UUID
        raw_candidate: str

    normal = outputs_for(generations)
    injected = (
        cast(
            JobOutput,
            UntrustedWireEnvelope(
                "summary",
                1,
                foreign_job.id,
                foreign_job.campaign_id,
                foreign_summary.id,
                '{"text":"Injected content must not publish."}',
            ),
        ),
        normal[1],
    )
    assert await publish_job(f.session, claim, injected)
    await f.session.commit()
    summary = await f.session.scalar(
        select(MemorySummary).where(MemorySummary.batch_id == item.id)
    )
    assert summary is not None
    assert summary.payload.text == "An immutable summary."
    assert summary.payload.text != "Injected content must not publish."
    assert summary.payload.text != "A foreign persisted summary."
    assert job.state == "succeeded"


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
    assert not await publish_job(f.session, claim, outputs_for(generations))
    await f.session.rollback()
    assert (
        await f.session.scalar(select(MemorySummary.id).where(MemorySummary.batch_id == batch_id))
        is None
    )


async def test_outer_rollback_removes_published_documents(history_fixture: HistoryFixture) -> None:
    f = history_fixture
    job, claim, generations, item, _state = await _claimed_job(f)
    batch_id, job_id = item.id, job.id
    assert await publish_job(f.session, claim, outputs_for(generations))
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
    assert await publish_job(f.session, claim, outputs_for(generations))
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
    job, claim, generations, item, state = await _claimed_job(
        f,
        raw_by_role={
            "summary": '{"text":"summary"}',
            "facts": json.dumps({"facts": [fact]}),
        },
    )
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
    await publish_job(f.session, claim, outputs_for(generations))
    if rollback:
        await f.session.rollback()
        assert await f.session.scalar(select(MemorySummary.id)) is None
        assert await f.session.scalar(select(MemoryFact.id)) is None
        assert await f.session.scalar(select(MemoryFactSource.fact_id)) is None
        assert await f.session.scalar(select(SourceEmbedding.id)) is None
        return
    await f.session.commit()
    stored = await f.session.scalar(select(MemoryFact).where(MemoryFact.batch_id == item.id))
    assert stored is not None
    queued = await f.session.scalar(
        select(SourceEmbedding).where(SourceEmbedding.memory_fact_id == stored.id)
    )
    assert stored.ordinal == 1
    assert queued is not None
    assert queued.text_hash
    assert state.last_compacted_batch_id is None
