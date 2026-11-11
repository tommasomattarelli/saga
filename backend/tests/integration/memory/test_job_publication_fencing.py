import pytest
from sqlalchemy import func, select, text

from app.memory.job_publication import JobOutput, PublicationLeaseExpiredError, publish_job
from app.models.memory_document import MemoryState, MemorySummary
from app.models.memory_fact import MemoryFact
from app.models.memory_job import MemoryJob
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_job_publication import _claimed_job


async def test_lease_expiring_during_publication_rolls_back_documents_and_cursor(
    history_fixture: HistoryFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.memory.job_activation import activate_artifact
    from app.models.turn import Turn

    f = history_fixture
    job, claim, generations, item, state = await _claimed_job(f)
    head = await f.session.get(Turn, item.source_head_turn_id)
    assert head is not None
    head = await f.turn(head)
    head = await f.turn(head)
    f.campaign.active_head_turn_id = head.id
    await f.session.commit()
    job_id, state_id = job.id, state.id

    async def expire(db, campaign, state, batch, checkpoint=None):
        activated = await activate_artifact(db, campaign, state, batch, checkpoint)
        assert activated
        await db.execute(
            text(
                "UPDATE memory_jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"
            ),
            {"id": job_id},
        )
        return activated

    monkeypatch.setattr("app.memory.job_publication.activate_artifact", expire)
    with pytest.raises(PublicationLeaseExpiredError):
        await publish_job(
            f.session,
            claim,
            (
                JobOutput(generations[0].id, '{"text":"A candidate."}'),
                JobOutput(generations[1].id, '{"facts":[]}'),
            ),
        )
    await f.session.rollback()
    assert await f.session.scalar(select(func.count()).select_from(MemorySummary)) == 0
    assert await f.session.scalar(select(func.count()).select_from(MemoryFact)) == 0
    loaded = await f.session.get(MemoryState, state_id)
    assert loaded is not None and loaded.last_compacted_batch_id is None
    loaded_job = await f.session.get(MemoryJob, job_id)
    assert loaded_job is not None and loaded_job.state == "running"
