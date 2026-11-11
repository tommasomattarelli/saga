import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy import select

from app.memory.history import history_path
from app.memory.job_claims import claim_job
from app.memory.job_publication import JobOutput, publish_job
from app.memory.job_requests import build_job_manifest, job_manifest_hash
from app.memory.producer_prompts import PRODUCER_VERSION
from app.models.embedding_index import EmbeddingIndex, EmbeddingRebuildState
from app.models.memory_batch import MemoryBatch, MemoryBatchTurn
from app.models.memory_document import MemoryState
from app.models.memory_fact import MemoryFact
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob
from app.models.source_embedding import EmbeddingWorkState, SourceEmbedding
from app.models.turn import Turn
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_job_publication import _claimed_job


def _index(fixture: HistoryFixture) -> EmbeddingIndex:
    return EmbeddingIndex(
        campaign_id=fixture.campaign.id,
        provider="openai",
        model="text-embedding-3-small",
        endpoint_identity="https://api.openai.com/v1",
        pipeline_version="embed-v1-legacy",
        dimension=384,
        is_active=True,
        rebuild_state=EmbeddingRebuildState.COMPLETED,
    )


def _fact_payload(content: str, source: str = "t1") -> str:
    return json.dumps(
        {
            "facts": [
                {
                    "content": content,
                    "category": "event",
                    "assertion_type": "occurrence",
                    "entities": [{"name": "Witness", "type": "npc", "role": "observer"}],
                    "attribution": [],
                    "source_turns": [source],
                    "temporal_references": [],
                    "importance": {"level": "ordinary", "reason": "A witnessed fact."},
                }
            ]
        }
    )


async def _publish_alternate_batch(
    fixture: HistoryFixture,
    turns: tuple[Turn, Turn],
    content: str,
) -> tuple[MemoryBatch, MemoryFact]:
    db = fixture.session
    campaign = fixture.campaign
    from app.memory.batch_input import load_turn_input

    source = await load_turn_input(db, campaign.id, tuple(turn.id for turn in turns))
    batch = MemoryBatch(
        id=uuid4(),
        campaign_id=campaign.id,
        policy_id=fixture.policy.id,
        previous_batch_id=None,
        source_head_turn_id=turns[-1].id,
        manifest_hash=source.source_hash(),
    )
    db.add(batch)
    await db.flush()
    db.add_all(
        MemoryBatchTurn(
            campaign_id=campaign.id, batch_id=batch.id, ordinal=ordinal, turn_id=turn.id
        )
        for ordinal, turn in enumerate(turns, start=1)
    )
    state = await db.get(MemoryState, campaign.active_memory_state_id)
    assert state is not None
    manifest = build_job_manifest(
        "batch", source, language="en", facts_policy=fixture.policy.payload.facts
    )
    job = MemoryJob(
        id=uuid4(),
        campaign_id=campaign.id,
        policy_id=fixture.policy.id,
        batch_id=batch.id,
        memory_state_id=state.id,
        context_epoch=campaign.context_epoch,
        kind="batch",
        logical_key=hashlib.sha256(content.encode()).hexdigest(),
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
    db.add(job)
    await db.commit()
    claim = await claim_job(db, campaign.id, job.id)
    assert claim is not None
    generations = tuple(
        MemoryGeneration(
            id=uuid4(),
            job_id=job.id,
            attempt_id=claim.attempt_id,
            campaign_id=campaign.id,
            policy_id=fixture.policy.id,
            batch_id=batch.id,
            role=role,
            provider="test",
            model="test",
        )
        for role in ("summary", "facts")
    )
    db.add_all(generations)
    await db.commit()
    assert await publish_job(
        db,
        claim,
        (
            JobOutput(generations[0].id, '{"text":"A branch memory summary."}'),
            JobOutput(generations[1].id, _fact_payload(content)),
        ),
    )
    await db.commit()
    fact = await db.scalar(select(MemoryFact).where(MemoryFact.batch_id == batch.id))
    assert fact is not None
    return batch, fact


async def _embed_fact(fixture: HistoryFixture, fact: MemoryFact, vector: list[float]) -> None:
    row = await fixture.session.scalar(
        select(SourceEmbedding).where(
            SourceEmbedding.campaign_id == fixture.campaign.id,
            SourceEmbedding.memory_fact_id == fact.id,
        )
    )
    assert row is not None
    row.embedding = vector
    row.work_state = EmbeddingWorkState.EMBEDDED
    await fixture.session.commit()


async def _recall(fixture: HistoryFixture, ancestry_ids: tuple[UUID, ...], limit: int = 3):
    from app.ai.embedding_config import legacy_space
    from app.memory.recall import PreparedRecallQuery
    from app.memory.semantic import search_similar_facts

    index = await fixture.session.scalar(
        select(EmbeddingIndex).where(EmbeddingIndex.campaign_id == fixture.campaign.id)
    )
    assert index is not None
    prepared = PreparedRecallQuery(
        fixture.campaign.user_id,
        fixture.campaign.id,
        index.id,
        legacy_space(),
        384,
        (1.0,) + (0.0,) * 383,
    )
    return await search_similar_facts(
        fixture.campaign.id,
        "query",
        fixture.session,
        limit=limit,
        query_embedding=prepared,
        ancestry_turn_ids=ancestry_ids,
    )


async def test_recall_rejects_cross_fork_batch_even_when_fact_cites_shared_turn(
    history_fixture: HistoryFixture,
) -> None:
    fixture = history_fixture
    fixture.session.add(_index(fixture))
    await fixture.session.commit()
    _job, claim, generations, batch, _state = await _claimed_job(fixture)
    fact_payload = _fact_payload("A future-branch event.", "t1")
    assert await publish_job(
        fixture.session,
        claim,
        (
            JobOutput(generations[0].id, '{"text":"Future branch summary."}'),
            JobOutput(generations[1].id, fact_payload),
        ),
    )
    await fixture.session.commit()
    fact = await fixture.session.scalar(select(MemoryFact).where(MemoryFact.batch_id == batch.id))
    assert fact is not None
    await _embed_fact(fixture, fact, [1.0] + [0.0] * 383)

    first = await fixture.session.get(Turn, claim.manifest.source_turn_ids[0])
    assert first is not None
    fork = await fixture.fork(first)
    branch_turn = await fixture.turn(first, continuation=fork, number=3)
    fixture.campaign.active_continuation_id = fork.id
    fixture.campaign.active_head_turn_id = branch_turn.id
    await fixture.session.commit()
    ancestry = tuple(
        turn.id
        for turn in await history_path(
            fixture.session, fixture.campaign.id, fixture.campaign.active_head_turn_id
        )
    )

    assert first.id in ancestry
    assert await _recall(fixture, ancestry) == []


async def test_recall_accepts_batch_wholly_shared_by_selected_history(
    history_fixture: HistoryFixture,
) -> None:
    fixture = history_fixture
    fixture.session.add(_index(fixture))
    await fixture.session.commit()
    _job, claim, generations, batch, _state = await _claimed_job(fixture)
    assert await publish_job(
        fixture.session,
        claim,
        (
            JobOutput(generations[0].id, '{"text":"Shared history summary."}'),
            JobOutput(generations[1].id, _fact_payload("A shared event.")),
        ),
    )
    await fixture.session.commit()
    fact = await fixture.session.scalar(select(MemoryFact).where(MemoryFact.batch_id == batch.id))
    assert fact is not None
    await _embed_fact(fixture, fact, [1.0] + [0.0] * 383)
    second = await fixture.session.get(Turn, claim.manifest.source_turn_ids[1])
    assert second is not None
    fork = await fixture.fork(second)
    branch_turn = await fixture.turn(second, continuation=fork, number=3)
    fixture.campaign.active_continuation_id = fork.id
    fixture.campaign.active_head_turn_id = branch_turn.id
    await fixture.session.commit()
    ancestry = tuple(
        turn.id
        for turn in await history_path(
            fixture.session, fixture.campaign.id, fixture.campaign.active_head_turn_id
        )
    )

    assert [item.id for item in await _recall(fixture, ancestry)] == [fact.id]


async def test_recall_filters_future_batch_before_similarity_top_k(
    history_fixture: HistoryFixture,
) -> None:
    fixture = history_fixture
    fixture.session.add(_index(fixture))
    await fixture.session.commit()
    _job, claim, generations, crossing_batch, _state = await _claimed_job(fixture)
    assert await publish_job(
        fixture.session,
        claim,
        (
            JobOutput(generations[0].id, '{"text":"Crossing summary."}'),
            JobOutput(generations[1].id, _fact_payload("Near but future.")),
        ),
    )
    await fixture.session.commit()
    crossing_fact = await fixture.session.scalar(
        select(MemoryFact).where(MemoryFact.batch_id == crossing_batch.id)
    )
    assert crossing_fact is not None
    await _embed_fact(fixture, crossing_fact, [1.0] + [0.0] * 383)

    first = await fixture.session.get(Turn, claim.manifest.source_turn_ids[0])
    assert first is not None
    fork = await fixture.fork(first)
    branch_turn = await fixture.turn(first, continuation=fork, number=3)
    fixture.campaign.active_continuation_id = fork.id
    fixture.campaign.active_head_turn_id = branch_turn.id
    await fixture.session.commit()
    active_batch, active_fact = await _publish_alternate_batch(
        fixture, (first, branch_turn), "Far but active."
    )
    assert active_batch.id != crossing_batch.id
    await _embed_fact(fixture, active_fact, [0.0, 1.0] + [0.0] * 382)
    ancestry = tuple(
        turn.id
        for turn in await history_path(
            fixture.session, fixture.campaign.id, fixture.campaign.active_head_turn_id
        )
    )

    facts = await _recall(fixture, ancestry, limit=1)

    assert [fact.id for fact in facts] == [active_fact.id]
