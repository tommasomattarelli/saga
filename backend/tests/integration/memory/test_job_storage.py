from uuid import uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.job_contracts import MemoryJobManifest
from app.models.campaign import Campaign, Difficulty
from app.models.memory_job import MemoryJob, MemoryJobAttempt
from tests.integration.memory.job_support import job_sources, new_attempt, new_job
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_batch_storage import batch


@pytest.mark.parametrize(
    "case", ["duplicate", "duplicate_input", "invalid_claim", "cross_campaign"]
)
async def test_jobs_reject_invalid_identity_and_claims(
    history_fixture: HistoryFixture, case: str
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job = new_job(f, turns, item, state)
    f.session.add(job)
    await f.session.commit()
    invalid = new_job(f, turns, item, state, key="e" * 64)
    if case == "duplicate":
        invalid.logical_key = job.logical_key
    elif case == "invalid_claim":
        invalid.state = "running"
    elif case == "cross_campaign":
        other = Campaign(
            id=uuid4(),
            user_id=f.campaign.user_id,
            world_slug="other",
            name="Other",
            difficulty=Difficulty.MEDIUM,
        )
        f.session.add(other)
        await f.session.commit()
        invalid.campaign_id = other.id
    f.session.add(invalid)
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()


@pytest.mark.parametrize("case", ["reversed", "incomplete", "hash"])
async def test_job_manifest_matches_ordered_batch_sources(
    history_fixture: HistoryFixture, case: str
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job = new_job(f, turns, item, state)
    if case == "hash":
        job.manifest = job.manifest.model_copy(update={"source_hash": "b" * 64})
    else:
        ids = tuple(
            turn.id for turn in (list(reversed(turns)) if case == "reversed" else turns[:1])
        )
        job.manifest = job.manifest.model_copy(update={"source_turn_ids": ids})
    f.session.add(job)
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()


async def test_attempts_and_manifest_survive_restart_style_reload(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job = new_job(f, turns, item, state)
    job.attempt_count, job.retry_cycle, job.cycle_attempt_count = 2, 1, 1
    f.session.add_all([job, new_attempt(job, 1), new_attempt(job, 2, cycle=1)])
    await f.session.commit()
    job_id, input_manifest = job.id, job.manifest
    f.session.expunge_all()
    loaded = await f.session.get(MemoryJob, job_id)
    assert loaded is not None and isinstance(loaded.manifest, MemoryJobManifest)
    assert loaded.manifest == input_manifest and loaded.attempt_count == 2
    attempts = list(
        (
            await f.session.scalars(
                select(MemoryJobAttempt)
                .where(MemoryJobAttempt.job_id == job_id)
                .order_by(MemoryJobAttempt.attempt_number)
            )
        ).all()
    )
    assert [(attempt.attempt_number, attempt.retry_cycle) for attempt in attempts] == [
        (1, 0),
        (2, 1),
    ]
    f.session.add(new_attempt(loaded, 2, cycle=1))
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()


@pytest.mark.parametrize("case", ["counter", "manifest"])
async def test_job_input_is_immutable_and_attempt_budget_cannot_reset(
    history_fixture: HistoryFixture, case: str
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job = new_job(f, turns, item, state)
    job.attempt_count = 2
    f.session.add(job)
    await f.session.commit()
    statement = update(MemoryJob).where(MemoryJob.id == job.id)
    statement = (
        statement.values(attempt_count=1)
        if case == "counter"
        else statement.values(
            manifest=job.manifest.model_copy(update={"instruction_text": "Rewritten"})
        )
    )
    with pytest.raises(IntegrityError):
        await f.session.execute(statement)
        await f.session.commit()
    await f.session.rollback()


@pytest.mark.parametrize("kind", ["batch", "global"])
async def test_jobs_require_matching_checkpoint_predecessors(
    history_fixture: HistoryFixture, kind: str
) -> None:
    f = history_fixture
    turns, first, state = await job_sources(f)
    if kind == "global":
        third = await f.turn(turns[-1])
        fourth = await f.turn(third)
        turns = [third, fourth]
        first = await batch(f, turns, first)
    job = new_job(f, turns, first, state)
    job.kind = kind
    job.previous_checkpoint_id = uuid4() if kind == "batch" else None
    f.session.add(job)
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()


async def test_job_schema_indexes_support_scoped_claim_reads(db_session: AsyncSession) -> None:
    indexes = set(
        (
            await db_session.execute(text("SELECT indexrelid::regclass::text FROM pg_index"))
        ).scalars()
    )
    assert {
        "ix_memory_jobs_policy_campaign",
        "ix_memory_jobs_batch_scope",
        "ix_memory_jobs_state_scope",
        "ix_memory_jobs_checkpoint_scope",
    } <= indexes
