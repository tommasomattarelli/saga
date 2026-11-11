from uuid import uuid4

from sqlalchemy import func, select

from app.memory.job_publication import JobOutput, publish_job
from app.memory.job_scheduler import coordinate_memory
from app.models.memory_document import MemoryState
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob
from app.models.turn import Turn
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_job_publication import _claimed_job


def outputs(generations: tuple[MemoryGeneration, ...]) -> tuple[JobOutput, ...]:
    return (
        JobOutput(generations[0].id, '{"text":"A shared historical memory."}'),
        JobOutput(generations[1].id, '{"facts":[]}'),
    )


async def test_ordinary_history_extension_does_not_detach_inflight_batch(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    job, claim, generations, item, state = await _claimed_job(f)
    head = await f.session.get(Turn, item.source_head_turn_id)
    assert head is not None
    head = await f.turn(head)
    head = await f.turn(head)
    f.campaign.active_head_turn_id = head.id
    await f.session.commit()
    assert await publish_job(f.session, claim, outputs(generations))
    await f.session.commit()
    assert job.activation_state == "active"
    assert state.last_compacted_batch_id == item.id
    assert state.revision == 1


async def test_late_artifact_reuse_respects_restore_raw_limit_without_new_calls(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    job, claim, generations, item, old_state = await _claimed_job(f)
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
    assert await publish_job(f.session, claim, outputs(generations))
    await f.session.commit()
    assert job.activation_state == "detached"
    assert await coordinate_memory(f.session, f.campaign.id) == ()
    assert restored.last_compacted_batch_id is None
    head = await f.session.get(Turn, item.source_head_turn_id)
    assert head is not None
    head = await f.turn(head)
    head = await f.turn(head)
    f.campaign.active_head_turn_id = head.id
    await f.session.commit()
    assert await coordinate_memory(f.session, f.campaign.id) == ()
    await f.session.commit()
    assert restored.last_compacted_batch_id == item.id
    assert old_state.last_compacted_batch_id is None
    assert await f.session.scalar(select(func.count()).select_from(MemoryGeneration)) == 2
    assert job.attempt_count == 1


async def test_crossing_fork_requires_different_batch_not_reuse_of_shared_fact_sources(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    old_job, claim, generations, item, old_state = await _claimed_job(f)
    first = await f.session.get(Turn, old_job.manifest.source_turn_ids[0])
    assert first is not None
    continuation = await f.fork(first)
    head = await f.turn(first, continuation=continuation)
    head = await f.turn(head, continuation=continuation)
    head = await f.turn(head, continuation=continuation)
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
    f.campaign.active_continuation_id = continuation.id
    f.campaign.active_head_turn_id = head.id
    await f.session.commit()
    assert await publish_job(f.session, claim, outputs(generations))
    await f.session.commit()
    (new_id,) = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()
    new_job = await f.session.get(MemoryJob, new_id)
    assert new_job is not None and new_job.id != old_job.id
    assert new_job.batch_id != item.id and new_job.attempt_count == 0
    assert new_job.manifest.source_turn_ids[0] == first.id
    assert new_job.manifest.source_turn_ids[1] != old_job.manifest.source_turn_ids[1]
    assert restored.last_compacted_batch_id is None
    assert old_state.last_compacted_batch_id is None
