import asyncio
import hashlib
from uuid import uuid4

from sqlalchemy import select, text

from app import dependencies
from app.ai.credentials import resolve_generation
from app.ai.generation_contracts import FormatMode, GenerationRequest, RawGenerationReceipt
from app.ai.generation_errors import Adapter
from app.ai.generation_execution_ledger import GenerationRecoveryPolicy
from app.memory.batch_input import load_batch_input
from app.memory.generation_ledger import DurableMemoryGenerationLedger
from app.memory.generation_receipts import encode_receipt
from app.memory.job_claims import claim_job, fail_claim, retry_job
from app.memory.job_requests import restore_job_requests
from app.memory.job_scheduler import coordinate_memory
from app.memory.producers import execute_memory_generation
from app.models.campaign import Campaign, Difficulty
from app.models.history import HistoryContinuation, MemoryPolicy
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob, MemoryJobAttempt
from app.models.user import User
from tests.integration.memory.job_support import (
    configure_local_generation,
    new_generation,
    persist_durable_generations,
    send_identity,
)
from tests.integration.memory.storage_support import HistoryFixture, production_policy
from tests.integration.memory.test_job_scheduler import active_history


async def _fail_claim_cycle(
    f: HistoryFixture, job: MemoryJob, *, valid_summary_at_cap: bool = False
) -> None:
    for index in range(f.policy.payload.jobs.max_attempts):
        claim = await claim_job(f.session, f.campaign.id, job.id)
        assert claim is not None
        if valid_summary_at_cap and index + 1 == f.policy.payload.jobs.max_attempts:
            await _persist_role_history(f, job, claim, "summary", valid_at_cap=True)
        assert await fail_claim(f.session, claim)
        await f.session.commit()
        if index + 1 < f.policy.payload.jobs.max_attempts:
            await f.session.execute(
                text(
                    "UPDATE memory_jobs SET next_attempt_at="
                    "clock_timestamp()-interval '1 second' WHERE id=:id"
                ),
                {"id": job.id},
            )
            await f.session.commit()
    await f.session.refresh(job)


async def _four_claim_fixture(f: HistoryFixture) -> HistoryFixture:
    campaign = Campaign(
        id=uuid4(),
        user_id=f.campaign.user_id,
        world_slug="test",
        name="Four claim cycle",
        difficulty=Difficulty.MEDIUM,
    )
    payload = production_policy()
    payload = payload.model_copy(
        update={
            "jobs": payload.jobs.model_copy(
                update={
                    "max_attempts": 4,
                    "retry_backoff_seconds": (1.0, 1.0, 1.0),
                }
            )
        }
    )
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


async def _scheduled_job(f: HistoryFixture) -> MemoryJob:
    await configure_local_generation(f)
    await active_history(f, 4)
    (job_id,) = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()
    job = await f.session.get(MemoryJob, job_id)
    assert job is not None
    return job


async def _persist_role_history(
    f: HistoryFixture,
    job: MemoryJob,
    claim,
    role: str,
    *,
    valid_at_cap: bool,
) -> None:
    assert job.execution_identity is not None
    cap = job.execution_identity.max_sends_per_result
    request_hash, request_snapshot = send_identity(job, role)
    attempt = await f.session.get(MemoryJobAttempt, claim.attempt_id)
    assert attempt is not None
    generations = []
    for number in range(1, cap + 1):
        generation = new_generation(job, attempt)
        generation.role = role
        generation.send_number = number
        generation.send_kind = "initial" if number == 1 else "correction"
        generation.request_identity_hash = request_hash
        generation.request_identity_snapshot = request_snapshot
        generation.format_mode = FormatMode.STRICT_NATIVE
        generation.status = "valid" if valid_at_cap and number == cap else "invalid"
        generation.outcome_reason = None if generation.status == "valid" else "validation_failed"
        if generation.status == "valid":
            receipt, candidate = encode_receipt(
                RawGenerationReceipt(
                    text='{"text":"candidate"}', raw_candidate='{"text":"candidate"}'
                )
            )
            generation.receipt = receipt
            generation.raw_candidate = candidate
            assert candidate is not None
            generation.raw_candidate_hash = hashlib.sha256(candidate.encode()).hexdigest()
        generations.append(generation)
    await persist_durable_generations(f.session, tuple(generations))


async def test_concurrent_workers_reserve_only_one_persistent_attempt(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    job = await _scheduled_job(f)

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
    f = await _four_claim_fixture(history_fixture)
    job = await _scheduled_job(f)
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
    for index in range(1, f.policy.payload.jobs.max_attempts):
        await f.session.execute(
            text(
                "UPDATE memory_jobs SET next_attempt_at=clock_timestamp()-interval '1 second' "
                "WHERE id=:id"
            ),
            {"id": job.id},
        )
        await f.session.commit()
        next_claim = await claim_job(f.session, f.campaign.id, job.id)
        await f.session.commit()
        assert next_claim is not None
        if index == 1:
            assert next_claim.token != first.token
            assert not await fail_claim(f.session, first)
        assert await fail_claim(f.session, next_claim)
        await f.session.commit()
    await f.session.refresh(job)
    assert job.state == "manual_retry_required" and job.attempt_count == 4
    assert job.terminal_at is None
    assert await claim_job(f.session, f.campaign.id, job.id) is None
    assert await retry_job(f.session, f.campaign.id, job.id)
    await f.session.commit()
    await f.session.refresh(job)
    assert (job.attempt_count, job.retry_cycle, job.cycle_attempt_count) == (4, 1, 0)
    assert job.terminal_at is None
    assert (
        await f.session.scalar(
            select(MemoryGeneration.id).where(MemoryGeneration.job_id == job.id)
        )
        is None
    )


async def test_claim_cycle_exhaustion_with_valid_capped_role_keeps_other_role_recoverable(
    history_fixture: HistoryFixture,
) -> None:
    f = await _four_claim_fixture(history_fixture)
    job = await _scheduled_job(f)
    await _fail_claim_cycle(f, job, valid_summary_at_cap=True)
    assert job.state == "manual_retry_required"
    assert job.terminal_at is None
    assert job.terminal_reason is None

    claim = await claim_job(f.session, f.campaign.id, job.id)
    assert claim is None
    assert await retry_job(f.session, f.campaign.id, job.id)
    await f.session.commit()
    assert job.retry_cycle == 1


async def test_corrected_candidate_survives_claim_cycle_and_is_reused_after_retry(
    history_fixture: HistoryFixture,
) -> None:
    f = await _four_claim_fixture(history_fixture)
    job = await _scheduled_job(f)
    first = await claim_job(f.session, f.campaign.id, job.id)
    assert first is not None and job.execution_identity is not None
    source = await load_batch_input(f.session, job.campaign_id, job.batch_id)
    prepared = restore_job_requests(job.manifest, source, f.policy.payload.facts)[0]
    user = await f.session.get(User, f.campaign.user_id)
    assert user is not None
    config, _, _ = resolve_generation(user)
    execution_identity = job.execution_identity
    affinity = execution_identity.result_identities["summary"].session_affinity
    max_sends = execution_identity.max_sends_per_result
    manifest = job.manifest
    await f.session.commit()

    class CorrectingProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            self.calls += 1
            if self.calls == 1:
                return RawGenerationReceipt(
                    text='{"wrong":"candidate"}',
                    raw_candidate='{"wrong":"candidate"}',
                )
            assert self.calls == 2
            assert request.identity.initial_prefix_hash != (
                execution_identity.result_identities["summary"].initial_prefix_hash
            )
            return RawGenerationReceipt(
                text='{"text":"INTERMEDIATE: The courier carries a sealed letter."}',
                raw_candidate='{"text":"INTERMEDIATE: The courier carries a sealed letter."}',
            )

    correcting_provider = CorrectingProvider()
    summary = await execute_memory_generation(
        prepared,
        provider=correcting_provider,
        ledger=DurableMemoryGenerationLedger(first),
        config=config,
        policy=GenerationRecoveryPolicy(max_sends),
        adapter=Adapter.LOCAL,
        session_affinity=affinity,
    )
    assert correcting_provider.calls == 2 and summary.send_number == 2
    assert await fail_claim(f.session, first)
    await f.session.commit()

    for _attempt_number in range(2, f.policy.payload.jobs.max_attempts + 1):
        await f.session.execute(
            text(
                "UPDATE memory_jobs SET next_attempt_at="
                "clock_timestamp()-interval '1 second' WHERE id=:id"
            ),
            {"id": job.id},
        )
        await f.session.commit()
        claim = await claim_job(f.session, f.campaign.id, job.id)
        assert claim is not None
        assert await fail_claim(f.session, claim)
        await f.session.commit()

    await f.session.refresh(job)
    assert job.state == "manual_retry_required"
    rows_before = list(
        await f.session.scalars(
            select(MemoryGeneration)
            .where(MemoryGeneration.job_id == job.id)
            .order_by(MemoryGeneration.send_number)
        )
    )
    assert [row.send_number for row in rows_before] == [1, 2]
    assert len({row.request_identity_snapshot for row in rows_before}) == 2
    assert rows_before[-1].status == "valid"
    assert await retry_job(f.session, f.campaign.id, job.id)
    await f.session.commit()

    retry_claim = await claim_job(f.session, f.campaign.id, job.id)
    assert retry_claim is not None
    retry_identity = job.execution_identity
    assert retry_identity is not None
    await f.session.commit()

    class FactsOnlyProvider:
        def __init__(self) -> None:
            self.roles: list[str] = []

        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            self.roles.append(request.role)
            assert request.role == "facts"
            return RawGenerationReceipt(text='{"facts":[]}', raw_candidate='{"facts":[]}')

    facts_provider = FactsOnlyProvider()
    for prepared_request in restore_job_requests(manifest, source, f.policy.payload.facts):
        await execute_memory_generation(
            prepared_request,
            provider=facts_provider,
            ledger=DurableMemoryGenerationLedger(retry_claim),
            config=config,
            policy=GenerationRecoveryPolicy(retry_identity.max_sends_per_result),
            adapter=Adapter.LOCAL,
            session_affinity=retry_identity.result_identities[
                prepared_request.kind
            ].session_affinity,
        )
    assert facts_provider.roles == ["facts"]
    await f.session.refresh(job)
    assert (job.state, job.attempt_count, job.retry_cycle, job.cycle_attempt_count) == (
        "running",
        f.policy.payload.jobs.max_attempts + 1,
        1,
        1,
    )


async def test_claim_cycle_exhaustion_is_definitive_only_when_all_required_roles_are_spent(
    history_fixture: HistoryFixture,
) -> None:
    f = await _four_claim_fixture(history_fixture)
    job = await _scheduled_job(f)

    for index in range(f.policy.payload.jobs.max_attempts):
        claim = await claim_job(f.session, f.campaign.id, job.id)
        assert claim is not None
        if index == f.policy.payload.jobs.max_attempts - 1:
            await _persist_role_history(f, job, claim, "summary", valid_at_cap=False)
            await _persist_role_history(f, job, claim, "facts", valid_at_cap=False)
        assert await fail_claim(f.session, claim)
        await f.session.commit()
        if index + 1 < f.policy.payload.jobs.max_attempts:
            await f.session.execute(
                text(
                    "UPDATE memory_jobs SET next_attempt_at="
                    "clock_timestamp()-interval '1 second' WHERE id=:id"
                ),
                {"id": job.id},
            )
            await f.session.commit()

    await f.session.refresh(job)
    assert job.state == "exhausted"
    assert job.terminal_reason == "required_result_send_budget_exhausted"
    terminal_at = job.terminal_at
    assert terminal_at is not None
    assert not await retry_job(f.session, f.campaign.id, job.id)
    assert await claim_job(f.session, f.campaign.id, job.id) is None
    await f.session.commit()
    await f.session.refresh(job)
    assert job.terminal_at == terminal_at
    assert (job.attempt_count, job.retry_cycle, job.cycle_attempt_count) == (
        f.policy.payload.jobs.max_attempts,
        0,
        f.policy.payload.jobs.max_attempts,
    )


async def test_corrupt_send_identity_blocks_instead_of_exhausting(
    history_fixture: HistoryFixture,
) -> None:
    f = await _four_claim_fixture(history_fixture)
    job = await _scheduled_job(f)

    for index in range(f.policy.payload.jobs.max_attempts):
        claim = await claim_job(f.session, f.campaign.id, job.id)
        assert claim is not None
        if index + 1 == f.policy.payload.jobs.max_attempts:
            await _persist_role_history(f, job, claim, "summary", valid_at_cap=False)
            await _persist_role_history(f, job, claim, "facts", valid_at_cap=False)
            rows = list(
                await f.session.scalars(
                    select(MemoryGeneration)
                    .where(MemoryGeneration.job_id == job.id)
                    .order_by(MemoryGeneration.role, MemoryGeneration.send_number)
                )
            )
            corrupt = next(row for row in rows if row.role == "summary" and row.send_number == 1)
            snapshot = corrupt.request_identity_snapshot
            corrupt.request_identity_snapshot = "{}"
            with f.session.no_autoflush:
                failed = await fail_claim(f.session, claim)
            corrupt.request_identity_snapshot = snapshot
        else:
            failed = await fail_claim(f.session, claim)
        assert failed
        await f.session.commit()
        if index + 1 < f.policy.payload.jobs.max_attempts:
            await f.session.execute(
                text(
                    "UPDATE memory_jobs SET next_attempt_at="
                    "clock_timestamp()-interval '1 second' WHERE id=:id"
                ),
                {"id": job.id},
            )
            await f.session.commit()

    await f.session.refresh(job)
    assert job.state == "blocked"
    assert job.terminal_at is None
    assert job.last_error == "Stored memory generation history is unsupported."


async def test_configuration_failure_blocks_until_explicit_retry(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    await configure_local_generation(f)
    await active_history(f, 4)
    (job_id,) = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()
    job = await f.session.get(MemoryJob, job_id)
    assert job is not None
    claim = await claim_job(f.session, f.campaign.id, job.id)
    assert claim is not None
    assert await fail_claim(f.session, claim, configuration_required=True)
    await f.session.commit()
    await f.session.refresh(job)
    assert job.state == "blocked" and job.claim_token is None
    assert await claim_job(f.session, f.campaign.id, job.id) is None
    assert not await retry_job(f.session, uuid4(), job.id)
    assert "configuration" in (job.last_error or "").lower()
