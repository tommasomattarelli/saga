from uuid import uuid4

from sqlalchemy import func, select

from app.memory.job_claims import claim_job, fail_claim
from app.memory.job_scheduler import coordinate_memory
from app.models.memory_batch import MemoryBatchTurn
from app.models.memory_document import MemoryState
from app.models.memory_job import MemoryJob
from tests.integration.memory.storage_support import HistoryFixture


async def active_history(f: HistoryFixture, count: int) -> MemoryState:
    head = None
    for number in range(count):
        head = await f.turn(head, number=number * 3 + 1)
    state = MemoryState(
        id=uuid4(),
        campaign_id=f.campaign.id,
        policy_id=f.policy.id,
        context_epoch=0,
    )
    f.session.add(state)
    await f.session.flush()
    f.campaign.active_memory_state_id = state.id
    f.campaign.active_head_turn_id = head.id if head else None
    await f.session.commit()
    return state


async def test_scheduler_counts_completed_nodes_and_reserves_only_oldest_batch(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    state = await active_history(f, 5)
    jobs = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()
    assert len(jobs) == 1
    job = await f.session.get(MemoryJob, jobs[0])
    assert job is not None and job.kind == "batch"
    assert job.attempt_count == 0 and state.last_compacted_batch_id is None
    assert await coordinate_memory(f.session, f.campaign.id) == jobs
    await f.session.commit()
    assert await f.session.scalar(select(func.count()).select_from(MemoryJob)) == 1
    members = list(
        await f.session.scalars(
            select(MemoryBatchTurn.turn_id)
            .where(MemoryBatchTurn.batch_id == job.batch_id)
            .order_by(MemoryBatchTurn.ordinal)
        )
    )
    assert tuple(members) == job.manifest.source_turn_ids
    assert len(members) == f.policy.payload.batch_turns
    assert f.campaign.active_head_turn_id not in members


async def test_restore_and_changed_templates_do_not_reset_existing_work(
    history_fixture: HistoryFixture,
    monkeypatch,
) -> None:
    f = history_fixture
    await active_history(f, 4)
    (job_id,) = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()
    claim = await claim_job(f.session, f.campaign.id, job_id)
    assert claim is not None
    await fail_claim(f.session, claim, configuration_required=True)
    await f.session.commit()
    restored = MemoryState(
        id=uuid4(),
        campaign_id=f.campaign.id,
        policy_id=f.policy.id,
        context_epoch=1,
    )
    f.session.add(restored)
    await f.session.flush()
    f.campaign.context_epoch = 1
    f.campaign.active_memory_state_id = restored.id
    await f.session.commit()

    def no_new_prompt(*args, **kwargs):
        raise AssertionError("An existing job must retain its original frozen instructions")

    monkeypatch.setattr("app.memory.job_scheduler.build_job_manifest", no_new_prompt)
    assert await coordinate_memory(f.session, f.campaign.id) == (job_id,)
    await f.session.commit()
    job = await f.session.get(MemoryJob, job_id, populate_existing=True)
    assert job is not None and job.state == "blocked" and job.attempt_count == 1


async def test_scheduler_leaves_legacy_runtime_and_incomplete_batches_alone(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    assert await coordinate_memory(f.session, f.campaign.id) == ()
    await active_history(f, 3)
    assert await coordinate_memory(f.session, f.campaign.id) == ()
    await f.session.commit()
    assert await f.session.scalar(select(func.count()).select_from(MemoryJob)) == 0
