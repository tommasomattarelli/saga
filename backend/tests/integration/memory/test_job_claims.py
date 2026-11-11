import asyncio
from uuid import uuid4

from sqlalchemy import select, text

from app import dependencies
from app.memory.job_claims import claim_job, fail_claim, retry_job
from app.models.memory_job import MemoryJobAttempt
from tests.integration.memory.job_support import job_sources, new_job
from tests.integration.memory.storage_support import HistoryFixture


async def test_concurrent_workers_reserve_only_one_persistent_attempt(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job = new_job(f, turns, item, state)
    f.session.add(job)
    await f.session.commit()

    async def claim():
        async with dependencies.async_session() as db:
            result = await claim_job(db, f.campaign.id, job.id)
            await db.commit()
            return result

    claims = await asyncio.gather(claim(), claim())
    assert sum(result is not None for result in claims) == 1
    await f.session.refresh(job)
    assert job.attempt_count == job.cycle_attempt_count == 1
    assert job.state == "running"
    attempts = list(await f.session.scalars(select(MemoryJobAttempt)))
    assert len(attempts) == 1 and attempts[0].state == "started"


async def test_expired_claim_consumes_budget_and_cannot_finish(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job = new_job(f, turns, item, state)
    f.session.add(job)
    await f.session.commit()
    first = await claim_job(f.session, f.campaign.id, job.id)
    await f.session.commit()
    assert first is not None
    await f.session.execute(
        text(
            "UPDATE memory_jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"
        ),
        {"id": job.id},
    )
    await f.session.commit()
    assert not await fail_claim(f.session, first)
    assert await claim_job(f.session, f.campaign.id, job.id) is None
    await f.session.commit()
    await f.session.refresh(job)
    assert job.attempt_count == 1 and job.state == "retry_wait"
    attempt = await f.session.get(MemoryJobAttempt, first.attempt_id)
    assert attempt is not None and attempt.state == "uncertain"
    await f.session.execute(
        text(
            "UPDATE memory_jobs SET next_attempt_at=clock_timestamp()-interval '1 second' WHERE id=:id"
        ),
        {"id": job.id},
    )
    await f.session.commit()
    second = await claim_job(f.session, f.campaign.id, job.id)
    await f.session.commit()
    assert second is not None and second.token != first.token
    assert not await fail_claim(f.session, first)
    assert await fail_claim(f.session, second)
    await f.session.commit()
    await f.session.refresh(job)
    assert job.state == "exhausted" and job.attempt_count == 2
    assert await claim_job(f.session, f.campaign.id, job.id) is None
    assert await retry_job(f.session, f.campaign.id, job.id)
    await f.session.commit()
    third = await claim_job(f.session, f.campaign.id, job.id)
    await f.session.commit()
    assert third is not None
    await f.session.refresh(job)
    assert (job.attempt_count, job.retry_cycle, job.cycle_attempt_count) == (3, 1, 1)
    assert not await retry_job(f.session, f.campaign.id, job.id)


async def test_configuration_failure_blocks_until_explicit_retry(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job = new_job(f, turns, item, state)
    f.session.add(job)
    await f.session.commit()
    claim = await claim_job(f.session, f.campaign.id, job.id)
    assert claim is not None
    assert await fail_claim(f.session, claim, configuration_required=True)
    await f.session.commit()
    await f.session.refresh(job)
    assert job.state == "blocked" and job.claim_token is None
    assert await claim_job(f.session, f.campaign.id, job.id) is None
    assert not await retry_job(f.session, uuid4(), job.id)
    assert "configuration" in (job.last_error or "").lower()
