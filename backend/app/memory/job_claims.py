from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload

from app.memory.job_contracts import MemoryJobManifest
from app.memory.production_policy import JobsPolicy, MemoryProductionPolicy
from app.models.campaign import Campaign
from app.models.history import MemoryPolicy
from app.models.memory_job import MemoryJob, MemoryJobAttempt


@dataclass(frozen=True)
class JobClaim:
    job_id: UUID
    campaign_id: UUID
    owner_id: UUID
    attempt_id: UUID
    token: UUID
    batch_id: UUID
    manifest: MemoryJobManifest
    policy: MemoryProductionPolicy


async def lock_campaign(db: AsyncSession, campaign_id: UUID) -> Campaign | None:
    return await db.scalar(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .options(raiseload("*"))
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def _lock_job(db: AsyncSession, campaign_id: UUID, job_id: UUID) -> MemoryJob | None:
    return await db.scalar(
        select(MemoryJob)
        .where(MemoryJob.id == job_id, MemoryJob.campaign_id == campaign_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def claim_job(db: AsyncSession, campaign_id: UUID, job_id: UUID) -> JobClaim | None:
    campaign = await lock_campaign(db, campaign_id)
    if campaign is None:
        return None
    job = await _lock_job(db, campaign_id, job_id)
    if job is None:
        return None
    policy = await db.get(MemoryPolicy, job.policy_id)
    if policy is None:
        return None
    now = await db.scalar(select(func.clock_timestamp()))
    assert isinstance(now, datetime)
    if job.state == "running" and job.lease_expires_at is not None:
        if job.lease_expires_at > now:
            return None
        attempt = await db.scalar(
            select(MemoryJobAttempt).where(
                MemoryJobAttempt.job_id == job.id,
                MemoryJobAttempt.claim_token == job.claim_token,
                MemoryJobAttempt.state == "started",
            )
        )
        if attempt is not None:
            _failure(job, attempt, policy.payload.jobs, now, uncertain=True)
    if job.state not in {"queued", "retry_wait"}:
        return None
    if job.next_attempt_at is not None and job.next_attempt_at > now:
        return None
    if job.cycle_attempt_count >= policy.payload.jobs.max_attempts:
        job.state = "exhausted"
        return None
    other = await db.scalar(
        select(MemoryJob.id).where(
            MemoryJob.id != job.id,
            MemoryJob.campaign_id == campaign_id,
            MemoryJob.memory_state_id == job.memory_state_id,
            MemoryJob.kind == job.kind,
            MemoryJob.state == "running",
            MemoryJob.lease_expires_at > now,
        )
    )
    if other is not None:
        return None
    token = uuid4()
    job.state, job.claim_token = "running", token
    job.lease_expires_at = now + timedelta(seconds=policy.payload.jobs.lease_seconds)
    job.attempt_count += 1
    job.cycle_attempt_count += 1
    job.next_attempt_at, job.last_error = None, None
    attempt = MemoryJobAttempt(
        id=uuid4(),
        job_id=job.id,
        campaign_id=campaign_id,
        attempt_number=job.attempt_count,
        retry_cycle=job.retry_cycle,
        claim_token=token,
        state="started",
        started_at=now,
    )
    db.add(attempt)
    await db.flush()
    return JobClaim(
        job.id,
        campaign_id,
        campaign.user_id,
        attempt.id,
        token,
        job.batch_id,
        job.manifest,
        policy.payload,
    )


async def load_claim(
    db: AsyncSession, claim: JobClaim
) -> tuple[MemoryJob, MemoryJobAttempt, datetime] | None:
    if await lock_campaign(db, claim.campaign_id) is None:
        return None
    job = await _lock_job(db, claim.campaign_id, claim.job_id)
    now = await db.scalar(select(func.clock_timestamp()))
    assert isinstance(now, datetime)
    if (
        job is None
        or job.state != "running"
        or job.claim_token != claim.token
        or job.lease_expires_at is None
        or job.lease_expires_at <= now
    ):
        return None
    attempt = await db.get(MemoryJobAttempt, claim.attempt_id, populate_existing=True)
    if (
        attempt is None
        or attempt.job_id != job.id
        or attempt.claim_token != claim.token
        or attempt.state != "started"
    ):
        return None
    return job, attempt, now


def _failure(
    job: MemoryJob,
    attempt: MemoryJobAttempt,
    policy: JobsPolicy,
    now: datetime,
    *,
    uncertain: bool = False,
    configuration_required: bool = False,
) -> None:
    reason = (
        "Memory generation requires a configuration update."
        if configuration_required
        else "Memory generation was interrupted."
        if uncertain
        else "Memory generation did not produce a valid result."
    )
    attempt.state = "uncertain" if uncertain else "failed"
    attempt.finished_at, attempt.error = now, reason
    job.claim_token, job.lease_expires_at = None, None
    job.last_error, job.next_attempt_at = reason, None
    if configuration_required:
        job.state = "blocked"
    elif job.cycle_attempt_count >= policy.max_attempts:
        job.state = "exhausted"
    else:
        job.state = "retry_wait"
        job.next_attempt_at = now + timedelta(
            seconds=policy.retry_backoff_seconds[job.cycle_attempt_count - 1]
        )


async def fail_claim(
    db: AsyncSession,
    claim: JobClaim,
    *,
    configuration_required: bool = False,
    uncertain: bool = False,
) -> bool:
    loaded = await load_claim(db, claim)
    if loaded is None:
        return False
    job, attempt, now = loaded
    _failure(
        job,
        attempt,
        claim.policy.jobs,
        now,
        configuration_required=configuration_required,
        uncertain=uncertain,
    )
    return True


async def retry_job(db: AsyncSession, campaign_id: UUID, job_id: UUID) -> bool:
    if await lock_campaign(db, campaign_id) is None:
        return False
    job = await _lock_job(db, campaign_id, job_id)
    if job is None or job.state not in {"blocked", "exhausted"}:
        return False
    job.retry_cycle += 1
    job.cycle_attempt_count = 0
    job.state, job.next_attempt_at, job.last_error = "queued", None, None
    return True


async def recover_jobs(db: AsyncSession, campaign_id: UUID) -> int:
    if await lock_campaign(db, campaign_id) is None:
        return 0
    now = await db.scalar(select(func.clock_timestamp()))
    assert isinstance(now, datetime)
    jobs = list(
        await db.scalars(
            select(MemoryJob)
            .where(
                MemoryJob.campaign_id == campaign_id,
                MemoryJob.state == "running",
                MemoryJob.lease_expires_at <= now,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    recovered = 0
    for job in jobs:
        policy = await db.get(MemoryPolicy, job.policy_id)
        attempt = await db.scalar(
            select(MemoryJobAttempt).where(
                MemoryJobAttempt.job_id == job.id,
                MemoryJobAttempt.claim_token == job.claim_token,
                MemoryJobAttempt.state == "started",
            )
        )
        if policy is not None and attempt is not None:
            _failure(job, attempt, policy.payload.jobs, now, uncertain=True)
            recovered += 1
    return recovered
