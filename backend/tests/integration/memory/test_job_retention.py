import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app import dependencies
from app.memory.job_retention import cleanup_terminal_generation_payloads
from app.models.campaign import Campaign, Difficulty
from app.models.history import HistoryContinuation, MemoryPolicy
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob, MemoryJobTerminalReason
from tests.integration.memory.storage_support import HistoryFixture, production_policy
from tests.integration.memory.test_job_publication import _claimed_job


async def _finish_job(
    fixture: HistoryFixture, job: MemoryJob, state: str, terminal_at: datetime
) -> None:
    job.state = state
    job.claim_token = None
    job.lease_expires_at = None
    job.terminal_at = terminal_at
    job.terminal_reason = (
        MemoryJobTerminalReason.REQUIRED_RESULT_SEND_BUDGET_EXHAUSTED
        if state == "exhausted"
        else None
    )
    await fixture.session.commit()


async def _sibling_campaign(fixture: HistoryFixture) -> HistoryFixture:
    campaign = Campaign(
        id=uuid4(),
        user_id=fixture.campaign.user_id,
        world_slug="test",
        name="Sibling",
        difficulty=Difficulty.MEDIUM,
    )
    fixture.session.add(campaign)
    await fixture.session.flush()
    payload = production_policy()
    policy = MemoryPolicy(
        id=uuid4(),
        campaign_id=campaign.id,
        schema_version=1,
        payload=payload,
        payload_hash=payload.policy_hash(),
    )
    root = HistoryContinuation(id=uuid4(), campaign_id=campaign.id)
    fixture.session.add_all([policy, root])
    await fixture.session.flush()
    campaign.memory_policy_id = policy.id
    campaign.active_continuation_id = root.id
    await fixture.session.commit()
    return HistoryFixture(fixture.session, campaign, policy, root)


@pytest.mark.parametrize("state", ["succeeded", "exhausted"])
async def test_terminal_payload_cleanup_preserves_evidence_and_is_idempotent(
    history_fixture: HistoryFixture, state: str
) -> None:
    fixture = history_fixture
    job, _, generations, _, _ = await _claimed_job(fixture)
    terminal_at = datetime.now(UTC) - timedelta(days=1)
    await _finish_job(fixture, job, state, terminal_at)
    generation_ids = [generation.id for generation in generations]
    expected_hashes = {generation.id: generation.raw_candidate_hash for generation in generations}

    assert await cleanup_terminal_generation_payloads(
        fixture.session, fixture.campaign.id, retention_days=1
    ) == len(generations)
    await fixture.session.commit()

    stored = list(
        await fixture.session.scalars(
            select(MemoryGeneration).where(MemoryGeneration.id.in_(generation_ids))
        )
    )
    assert len(stored) == len(generations)
    for generation in stored:
        assert generation.raw_candidate is None
        assert generation.receipt is None
        assert generation.raw_candidate_hash == expected_hashes[generation.id]
        assert generation.status == "valid"
        assert generation.request_identity_snapshot is not None
        assert generation.request_identity_hash is not None
        assert generation.send_number == 1
        assert generation.outcome_reason is None
        assert generation.diagnostics is None
        assert generation.normalization is None
        assert generation.input_tokens is None
        assert generation.output_tokens is None
        assert generation.cost is None
        assert generation.latency_ms is None
    assert job.terminal_at == terminal_at
    assert (
        await cleanup_terminal_generation_payloads(
            fixture.session, fixture.campaign.id, retention_days=1
        )
        == 0
    )


async def test_detached_success_is_retained_from_terminal_at(
    history_fixture: HistoryFixture,
) -> None:
    fixture = history_fixture
    job, _, generations, _, _ = await _claimed_job(fixture)
    job.activation_state = "detached"
    await _finish_job(fixture, job, "succeeded", datetime.now(UTC) - timedelta(days=1, seconds=1))

    assert await cleanup_terminal_generation_payloads(
        fixture.session, fixture.campaign.id, retention_days=1
    ) == len(generations)


async def test_cleanup_leaves_other_campaign_payloads_intact(
    history_fixture: HistoryFixture,
) -> None:
    fixture = history_fixture
    sibling = await _sibling_campaign(fixture)
    job, _, generations, _, _ = await _claimed_job(fixture)
    sibling_job, _, sibling_generations, _, _ = await _claimed_job(sibling)
    terminal_at = datetime.now(UTC) - timedelta(days=2)
    await _finish_job(fixture, job, "succeeded", terminal_at)
    await _finish_job(sibling, sibling_job, "succeeded", terminal_at)

    assert await cleanup_terminal_generation_payloads(
        fixture.session, fixture.campaign.id, retention_days=1
    ) == len(generations)
    await fixture.session.commit()

    for generation in generations:
        await fixture.session.refresh(generation)
        assert generation.raw_candidate is None
        assert generation.receipt is None
    for generation in sibling_generations:
        await fixture.session.refresh(generation)
        assert generation.raw_candidate is not None
        assert generation.receipt is not None


@pytest.mark.parametrize(
    "state",
    ["blocked", "manual_retry_required", "running", "queued", "retry_wait"],
)
async def test_recoverable_job_payloads_are_not_cleaned(
    history_fixture: HistoryFixture,
    state: str,
) -> None:
    fixture = history_fixture
    job, _, generations, _, _ = await _claimed_job(fixture)
    job.state = state
    if state != "running":
        job.claim_token = None
        job.lease_expires_at = None
    await fixture.session.commit()

    assert (
        await cleanup_terminal_generation_payloads(
            fixture.session, fixture.campaign.id, retention_days=1
        )
        == 0
    )
    await fixture.session.commit()
    for generation in generations:
        await fixture.session.refresh(generation)
        assert generation.raw_candidate is not None
        assert generation.receipt is not None
    assert job.terminal_at is None


async def test_terminal_clock_controls_boundary_not_updated_at(
    history_fixture: HistoryFixture,
) -> None:
    fixture = history_fixture
    job, _, generations, _, _ = await _claimed_job(fixture)
    await _finish_job(fixture, job, "succeeded", datetime.now(UTC) - timedelta(hours=23))
    await fixture.session.execute(
        text(
            "UPDATE memory_jobs SET updated_at = clock_timestamp() - interval '30 days' WHERE id = :id"
        ),
        {"id": job.id},
    )
    await fixture.session.commit()

    assert (
        await cleanup_terminal_generation_payloads(
            fixture.session, fixture.campaign.id, retention_days=1
        )
        == 0
    )
    await fixture.session.commit()
    for generation in generations:
        await fixture.session.refresh(generation)
        assert generation.raw_candidate is not None


async def test_cleanup_includes_exact_database_retention_boundary(
    history_fixture: HistoryFixture,
) -> None:
    fixture = history_fixture
    job, _, generations, _, _ = await _claimed_job(fixture)
    await fixture.session.execute(
        text(
            "UPDATE memory_jobs SET state = 'succeeded', claim_token = NULL, "
            "lease_expires_at = NULL, terminal_at = clock_timestamp() - interval '1 day' "
            "WHERE id = :id"
        ),
        {"id": job.id},
    )
    await fixture.session.commit()

    assert await cleanup_terminal_generation_payloads(
        fixture.session, fixture.campaign.id, retention_days=1
    ) == len(generations)


async def test_concurrent_cleanup_clears_each_generation_once(
    history_fixture: HistoryFixture,
) -> None:
    fixture = history_fixture
    job, _, generations, _, _ = await _claimed_job(fixture)
    await _finish_job(fixture, job, "succeeded", datetime.now(UTC) - timedelta(days=2))

    async def cleanup() -> int:
        async with dependencies.async_session() as db:
            count = await cleanup_terminal_generation_payloads(
                db, fixture.campaign.id, retention_days=1
            )
            await db.commit()
            return count

    counts = await asyncio.gather(cleanup(), cleanup())
    assert sum(counts) == len(generations)
    assert sorted(counts) == [0, len(generations)]


async def test_terminal_cleanup_guard_rejects_unpaired_clear_and_evidence_mutation(
    history_fixture: HistoryFixture,
) -> None:
    fixture = history_fixture
    job, _, generations, _, _ = await _claimed_job(fixture)
    await _finish_job(fixture, job, "succeeded", datetime.now(UTC) - timedelta(days=2))
    generation = generations[0]
    generation_id = generation.id
    campaign_id = fixture.campaign.id

    with pytest.raises(IntegrityError):
        await fixture.session.execute(
            text("UPDATE memory_generations SET raw_candidate = NULL WHERE id = :id"),
            {"id": generation_id},
        )
    await fixture.session.rollback()

    with pytest.raises(IntegrityError):
        await fixture.session.execute(
            text("UPDATE memory_generations SET diagnostics = '{}'::jsonb WHERE id = :id"),
            {"id": generation_id},
        )
    await fixture.session.rollback()

    assert await cleanup_terminal_generation_payloads(
        fixture.session, campaign_id, retention_days=1
    ) == len(generations)
    await fixture.session.commit()
    with pytest.raises(IntegrityError):
        await fixture.session.execute(
            text("UPDATE memory_generations SET raw_candidate = 'restored' WHERE id = :id"),
            {"id": generation_id},
        )
    await fixture.session.rollback()
