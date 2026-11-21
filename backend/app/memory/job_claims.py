from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload

from app.ai.credentials import resolve_generation
from app.ai.router import get_generation_recovery_policy
from app.config_loader import load_saga_config
from app.exceptions import ValidationError
from app.memory.batch_input import load_batch_input
from app.memory.job_claim_transitions import (
    CANNOT_BIND_IDENTITY_REASON,
    INCOMPATIBLE_JOB_REASON,
    UNSUPPORTED_HISTORY_REASON,
    UNSUPPORTED_IDENTITY_REASON,
    apply_claim_limit_transition,
    fail_claim_transition,
    inspect_role_sends,
    is_integrity_block_reason,
)
from app.memory.job_contracts import MemoryJobManifest
from app.memory.job_identity import build_execution_identity
from app.memory.job_requests import restore_job_requests
from app.memory.production_policy import MemoryProductionPolicy
from app.models.campaign import Campaign
from app.models.history import MemoryPolicy
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob, MemoryJobAttempt
from app.models.user import User


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
            await fail_claim_transition(db, job, attempt, policy.payload.jobs, now, uncertain=True)
    if job.state not in {"queued", "retry_wait"}:
        return None
    if (
        job.execution_contract_version != 1
        or job.execution_identity is None
        or job.execution_identity_hash is None
        or job.execution_identity_version is None
    ):
        _block_unsupported_identity(job)
        return None
    try:
        job.execution_identity.verify(job.execution_identity_version, job.execution_identity_hash)
    except ValueError:
        _block_unsupported_identity(job)
        return None
    expected_roles = {"summary", "facts"} if job.kind == "batch" else {"global"}
    if set(job.execution_identity.result_identities) != expected_roles:
        _block_unsupported_identity(job)
        return None
    if job.next_attempt_at is not None and job.next_attempt_at > now:
        return None
    if job.cycle_attempt_count >= policy.payload.jobs.max_attempts:
        await apply_claim_limit_transition(db, job, now)
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


async def fail_claim(
    db: AsyncSession,
    claim: JobClaim,
    *,
    configuration_required: bool = False,
    uncertain: bool = False,
    blocked_reason: str | None = None,
) -> bool:
    loaded = await load_claim(db, claim)
    if loaded is None:
        return False
    job, attempt, now = loaded
    await fail_claim_transition(
        db,
        job,
        attempt,
        claim.policy.jobs,
        now,
        configuration_required=configuration_required,
        uncertain=uncertain,
        blocked_reason=blocked_reason,
    )
    return True


async def retry_job(db: AsyncSession, campaign_id: UUID, job_id: UUID) -> bool:
    if await lock_campaign(db, campaign_id) is None:
        return False
    job = await _lock_job(db, campaign_id, job_id)
    if (
        job is None
        or job.state not in {"blocked", "manual_retry_required"}
        or job.execution_contract_version != 1
    ):
        return False
    if job.state == "blocked" and is_integrity_block_reason(job.last_error):
        return False
    campaign = await db.get(Campaign, campaign_id)
    policy = await db.get(MemoryPolicy, job.policy_id)
    user = await db.get(User, campaign.user_id) if campaign is not None else None
    if campaign is None or policy is None or user is None:
        job.state = "blocked"
        job.last_error = "Memory generation requires updated provider configuration."
        return False
    try:
        config, _, _ = resolve_generation(user)
    except ValidationError:
        job.state = "blocked"
        job.last_error = "Memory generation requires updated provider configuration."
        return False
    try:
        source = await load_batch_input(db, campaign_id, job.batch_id)
        requests = restore_job_requests(job.manifest, source, policy.payload.facts)
    except (PydanticValidationError, ValueError):
        job.state = "blocked"
        job.last_error = INCOMPATIBLE_JOB_REASON
        return False
    cap = (
        job.execution_identity.max_sends_per_result
        if job.execution_identity
        else (get_generation_recovery_policy().max_sends_per_result)
    )
    generation_config = load_saga_config().get("generation", {})
    affinity_setting = generation_config.get("openrouter_session_affinity", True)
    if not isinstance(affinity_setting, bool):
        job.state = "blocked"
        job.last_error = "Memory generation requires updated provider configuration."
        return False
    try:
        identity = build_execution_identity(
            job.manifest,
            source,
            policy.payload.facts,
            config,
            cap,
            campaign_id,
            openrouter_affinity_enabled=affinity_setting,
        )
    except (PydanticValidationError, ValueError):
        job.state = "blocked"
        job.last_error = INCOMPATIBLE_JOB_REASON
        return False
    if job.execution_identity is None:
        if job.attempt_count != 0:
            job.last_error = CANNOT_BIND_IDENTITY_REASON
            return False
        rows = list(
            await db.scalars(select(MemoryGeneration).where(MemoryGeneration.job_id == job.id))
        )
        if rows:
            job.last_error = CANNOT_BIND_IDENTITY_REASON
            return False
    else:
        try:
            if (
                job.execution_identity_hash is None
                or job.execution_identity_version is None
                or identity.model_dump(mode="json")
                != job.execution_identity.model_dump(mode="json")
            ):
                job.state = "blocked"
                job.last_error = (
                    "Memory generation settings differ from this job's frozen identity."
                )
                return False
            job.execution_identity.verify(
                job.execution_identity_version, job.execution_identity_hash
            )
        except ValueError:
            job.state = "blocked"
            job.last_error = INCOMPATIBLE_JOB_REASON
            return False
        if set(job.execution_identity.result_identities) != {request.kind for request in requests}:
            job.state = "blocked"
            job.last_error = UNSUPPORTED_IDENTITY_REASON
            return False
    if tuple(request.kind for request in requests) != (
        ("summary", "facts") if job.kind == "batch" else ("global",)
    ):
        job.state = "blocked"
        job.last_error = UNSUPPORTED_IDENTITY_REASON
        return False

    rows = list(
        await db.scalars(
            select(MemoryGeneration)
            .where(MemoryGeneration.job_id == job.id)
            .order_by(MemoryGeneration.role, MemoryGeneration.send_number)
        )
    )
    required_roles = tuple(request.kind for request in requests)
    if any(row.role not in required_roles or row.send_number is None for row in rows):
        job.state = "blocked"
        job.last_error = UNSUPPORTED_HISTORY_REASON
        return False
    role_sends = inspect_role_sends(tuple(rows), required_roles, identity)
    if role_sends is None:
        job.state = "blocked"
        job.last_error = UNSUPPORTED_HISTORY_REASON
        return False
    for role in required_roles:
        sends = role_sends[role]
        if sends.send_count > cap or (sends.send_count >= cap and not sends.reusable_candidate):
            job.last_error = "No memory generation sends remain for a required result."
            return False

    if job.execution_identity is None:
        job.execution_identity = identity
        job.execution_identity_hash = identity.digest(1)
        job.execution_identity_version = 1
    job.retry_cycle += 1
    job.cycle_attempt_count = 0
    job.state, job.next_attempt_at, job.last_error = "queued", None, None
    return True


def _block_unsupported_identity(job: MemoryJob) -> None:
    job.state = "blocked"
    job.last_error = UNSUPPORTED_IDENTITY_REASON


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
            await fail_claim_transition(db, job, attempt, policy.payload.jobs, now, uncertain=True)
            recovered += 1
    return recovered
