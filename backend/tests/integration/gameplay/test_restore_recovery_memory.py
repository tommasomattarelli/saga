from sqlalchemy import func, select, text

from app.memory.job_claims import recover_jobs
from app.memory.job_publication import JobOutput, publish_job
from app.memory.job_scheduler import coordinate_memory
from app.models.memory_document import MemoryState
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob, MemoryJobAttempt
from app.models.turn import Turn
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.storage_support import (
    history_fixture as history_fixture,  # noqa: F401
)
from tests.integration.memory.test_job_publication import _claimed_job


async def test_api_restore_reuses_late_batch_inside_saved_raw_limit_without_new_attempt(
    auth_client,
    history_fixture: HistoryFixture,
) -> None:
    fixture = history_fixture
    job, claim, generations, batch, old_state = await _claimed_job(fixture)
    first = await fixture.session.get(Turn, job.manifest.source_turn_ids[0])
    assert first is not None
    head = await fixture.session.get(Turn, job.manifest.source_turn_ids[-1])
    assert head is not None
    head = await fixture.turn(head, number=3)
    head = await fixture.turn(head, number=4)
    fixture.campaign.active_head_turn_id = head.id
    await fixture.session.commit()

    saved = await auth_client.post(
        f"/api/saves/{fixture.campaign.id}", json={"name": "Four raw turns"}
    )
    assert saved.status_code == 201, saved.text
    loaded = await auth_client.post(f"/api/saves/{fixture.campaign.id}/load/{saved.json()['id']}")
    assert loaded.status_code == 200, loaded.text

    assert await publish_job(
        fixture.session,
        claim,
        (
            JobOutput(generations[0].id, '{"text":"A shared historical memory."}'),
            JobOutput(generations[1].id, '{"facts":[]}'),
        ),
    )
    await fixture.session.commit()
    await fixture.session.refresh(fixture.campaign)
    restored = await fixture.session.get(
        MemoryState, fixture.campaign.active_memory_state_id, populate_existing=True
    )
    assert restored is not None
    assert restored.last_compacted_batch_id is None

    assert await coordinate_memory(fixture.session, fixture.campaign.id) == ()
    await fixture.session.commit()
    await fixture.session.refresh(restored)
    await fixture.session.refresh(job)
    assert restored.last_compacted_batch_id == batch.id
    assert restored.revision == 1
    assert old_state.last_compacted_batch_id is None
    assert job.attempt_count == 1
    assert await fixture.session.scalar(select(func.count()).select_from(MemoryGeneration)) == 2


async def test_api_restore_worker_recovery_counts_uncertain_attempt_and_fences_stale_claim(
    auth_client,
    history_fixture: HistoryFixture,
) -> None:
    fixture = history_fixture
    job, old_claim, generations, batch, _state = await _claimed_job(fixture)
    job_id = job.id
    attempt_id = old_claim.attempt_id
    saved = await auth_client.post(
        f"/api/saves/{fixture.campaign.id}", json={"name": "Interrupted batch"}
    )
    assert saved.status_code == 201, saved.text
    loaded = await auth_client.post(f"/api/saves/{fixture.campaign.id}/load/{saved.json()['id']}")
    assert loaded.status_code == 200, loaded.text

    await fixture.session.execute(
        text(
            "UPDATE memory_jobs SET lease_expires_at="
            "clock_timestamp()-interval '1 second' WHERE id=:job_id"
        ),
        {"job_id": job.id},
    )
    await fixture.session.commit()

    from app import dependencies

    async with dependencies.async_session() as fresh_worker_session:
        assert await recover_jobs(fresh_worker_session, fixture.campaign.id) == 1
        await fresh_worker_session.commit()

    await fixture.session.refresh(job)
    old_attempt = await fixture.session.get(MemoryJobAttempt, old_claim.attempt_id)
    assert old_attempt is not None and old_attempt.state == "uncertain"
    assert job.state == "retry_wait" and job.attempt_count == 1
    assert job.claim_token is None and job.lease_expires_at is None

    assert not await publish_job(
        fixture.session,
        old_claim,
        (
            JobOutput(generations[0].id, '{"text":"Must remain unpublished."}'),
            JobOutput(generations[1].id, '{"facts":[]}'),
        ),
    )
    await fixture.session.commit()
    assert (
        await fixture.session.scalar(
            select(MemoryJob.id).where(MemoryJob.id == job_id, MemoryJob.state == "retry_wait")
        )
        == job_id
    )
    refreshed_job = await fixture.session.get(MemoryJob, job_id, populate_existing=True)
    assert refreshed_job is not None and refreshed_job.attempt_count == 1
    assert (
        await fixture.session.scalar(
            select(MemoryGeneration.id).where(MemoryGeneration.attempt_id == attempt_id)
        )
        is not None
    )
    assert (
        await fixture.session.scalar(
            select(func.count())
            .select_from(MemoryGeneration)
            .where(MemoryGeneration.batch_id == batch.id)
        )
        == 2
    )
