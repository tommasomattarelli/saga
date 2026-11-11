from sqlalchemy import func, select, text

from app.memory.job_claims import JobClaim, claim_job, fail_claim
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob, MemoryJobAttempt
from app.models.turn import Turn
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.storage_support import (
    history_fixture as history_fixture,  # noqa: F401
)
from tests.integration.memory.test_job_publication import _claimed_job


async def _four_turn_memory_history(fixture: HistoryFixture) -> tuple[MemoryJob, JobClaim]:
    job, claim, _, _, _ = await _claimed_job(fixture)
    head = await fixture.session.get(Turn, job.manifest.source_turn_ids[-1])
    assert head is not None
    head = await fixture.turn(head, number=3)
    head = await fixture.turn(head, number=4)
    fixture.campaign.active_head_turn_id = head.id
    fixture.campaign.turn_number = 4
    await fixture.session.commit()
    return job, claim


async def _save_and_restore_twice(client, fixture: HistoryFixture, job: MemoryJob) -> dict:
    job_id = job.id
    original = (job.state, job.attempt_count, job.retry_cycle)
    attempt_ids = set(
        await fixture.session.scalars(
            select(MemoryJobAttempt.id).where(MemoryJobAttempt.job_id == job_id)
        )
    )
    generation_count = await fixture.session.scalar(
        select(func.count()).select_from(MemoryGeneration).where(MemoryGeneration.job_id == job_id)
    )
    saved = await client.post(
        f"/api/saves/{fixture.campaign.id}", json={"name": "Failed memory job"}
    )
    assert saved.status_code == 201, saved.text
    for _ in range(2):
        loaded = await client.post(f"/api/saves/{fixture.campaign.id}/load/{saved.json()['id']}")
        assert loaded.status_code == 200, loaded.text
        await fixture.session.refresh(job)
        assert set(
            await fixture.session.scalars(
                select(MemoryJob.id).where(MemoryJob.batch_id == job.batch_id)
            )
        ) == {job_id}
        assert (job.state, job.attempt_count, job.retry_cycle) == original
        assert (
            set(
                await fixture.session.scalars(
                    select(MemoryJobAttempt.id).where(MemoryJobAttempt.job_id == job_id)
                )
            )
            == attempt_ids
        )
        assert (
            await fixture.session.scalar(
                select(func.count())
                .select_from(MemoryGeneration)
                .where(MemoryGeneration.job_id == job_id)
            )
            == generation_count
        )
    return loaded.json()


async def _assert_retry_budget_unchanged(fixture: HistoryFixture, job: MemoryJob) -> None:
    await fixture.session.refresh(job)
    attempts = list(
        await fixture.session.scalars(
            select(MemoryJobAttempt)
            .where(MemoryJobAttempt.job_id == job.id)
            .order_by(MemoryJobAttempt.attempt_number)
        )
    )
    assert [attempt.attempt_number for attempt in attempts] == list(
        range(1, job.attempt_count + 1)
    )
    assert (
        await fixture.session.scalar(
            select(func.count())
            .select_from(MemoryGeneration)
            .where(MemoryGeneration.job_id == job.id)
        )
        == 2
    )


async def _explicit_retry(client, fixture: HistoryFixture, loaded: dict) -> dict:
    response = await client.post(
        f"/api/campaigns/{fixture.campaign.id}/memory/retry",
        json={
            "expected_head_turn_id": loaded["active_head_turn_id"],
            "expected_context_epoch": loaded["context_epoch"],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["retried"] == 1
    return response.json()


async def test_repeated_restore_preserves_blocked_job_budget_until_explicit_retry(
    auth_client, history_fixture: HistoryFixture
) -> None:
    fixture = history_fixture
    job, claim = await _four_turn_memory_history(fixture)
    job_id = job.id
    assert await fail_claim(fixture.session, claim, configuration_required=True)
    await fixture.session.commit()
    attempt_count, retry_cycle = job.attempt_count, job.retry_cycle

    loaded = await _save_and_restore_twice(auth_client, fixture, job)
    await _assert_retry_budget_unchanged(fixture, job)
    assert job.id == job_id
    assert (job.state, job.attempt_count, job.retry_cycle) == (
        "blocked",
        attempt_count,
        retry_cycle,
    )

    await _explicit_retry(auth_client, fixture, loaded)
    await fixture.session.refresh(job)
    assert job.id == job_id
    assert job.state == "queued"
    assert job.retry_cycle == retry_cycle + 1
    assert job.attempt_count == attempt_count
    next_claim = await claim_job(fixture.session, fixture.campaign.id, job_id)
    assert next_claim is not None
    await fixture.session.commit()
    await fixture.session.refresh(job)
    assert (job.state, job.attempt_count, job.retry_cycle, job.cycle_attempt_count) == (
        "running",
        attempt_count + 1,
        retry_cycle + 1,
        1,
    )


async def test_repeated_restore_preserves_exhausted_job_budget_until_explicit_retry(
    auth_client, history_fixture: HistoryFixture
) -> None:
    fixture = history_fixture
    job, first = await _four_turn_memory_history(fixture)
    job_id = job.id
    assert await fail_claim(fixture.session, first)
    await fixture.session.commit()
    await fixture.session.execute(
        text(
            "UPDATE memory_jobs SET next_attempt_at="
            "clock_timestamp()-interval '1 second' WHERE id=:job_id"
        ),
        {"job_id": job_id},
    )
    await fixture.session.commit()
    second = await claim_job(fixture.session, fixture.campaign.id, job_id)
    assert second is not None
    assert await fail_claim(fixture.session, second)
    await fixture.session.commit()
    await fixture.session.refresh(job)
    assert job.state == "exhausted" and job.attempt_count == 2
    attempt_ids = set(
        await fixture.session.scalars(
            select(MemoryJobAttempt.id).where(MemoryJobAttempt.job_id == job_id)
        )
    )

    loaded = await _save_and_restore_twice(auth_client, fixture, job)
    await _assert_retry_budget_unchanged(fixture, job)
    await fixture.session.refresh(job)
    assert job.id == job_id
    assert (job.state, job.attempt_count, job.retry_cycle) == ("exhausted", 2, 0)
    assert (
        set(
            await fixture.session.scalars(
                select(MemoryJobAttempt.id).where(MemoryJobAttempt.job_id == job_id)
            )
        )
        == attempt_ids
    )

    await _explicit_retry(auth_client, fixture, loaded)
    await fixture.session.refresh(job)
    assert job.id == job_id
    assert (job.state, job.attempt_count, job.retry_cycle, job.cycle_attempt_count) == (
        "queued",
        2,
        1,
        0,
    )
    next_claim = await claim_job(fixture.session, fixture.campaign.id, job_id)
    assert next_claim is not None
    await fixture.session.commit()
    await fixture.session.refresh(job)
    assert (job.state, job.attempt_count, job.retry_cycle, job.cycle_attempt_count) == (
        "running",
        3,
        1,
        1,
    )
