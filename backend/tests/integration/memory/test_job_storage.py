from collections.abc import MutableMapping
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.job_contracts import MemoryGenerationIdentitySnapshot, MemoryJobManifest
from app.models.campaign import Campaign, Difficulty
from app.models.memory_job import MemoryJob, MemoryJobAttempt
from tests.integration.memory.job_support import (
    job_sources,
    new_attempt,
    new_identity_job,
    new_job,
)
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


async def test_execution_identity_is_typed_hash_checked_and_frozen(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job, _, identity_hash, _ = await new_identity_job(f, turns, item, state)

    loaded = await f.session.get(MemoryJob, job.id)
    assert loaded is not None
    assert loaded.execution_identity is not None
    assert loaded.execution_identity_version == 1
    loaded.execution_identity.verify(loaded.execution_identity_version, identity_hash)
    identities = cast(
        MutableMapping[str, MemoryGenerationIdentitySnapshot],
        loaded.execution_identity.result_identities,
    )
    with pytest.raises(TypeError):
        identities["summary"] = identities["facts"]
    loaded.execution_identity.verify(loaded.execution_identity_version, identity_hash)
    identity_json = loaded.execution_identity.model_dump_json()
    with pytest.raises(ValueError, match="hash"):
        loaded.execution_identity.verify(1, "0" * 64)
    with pytest.raises(ValueError, match="Unsupported"):
        loaded.execution_identity.digest(2)

    loaded.execution_identity_hash = "0" * 64
    with pytest.raises(ValueError, match="does not match"):
        await f.session.commit()
    await f.session.rollback()
    await f.session.refresh(loaded)

    with pytest.raises(IntegrityError):
        await f.session.execute(
            text("UPDATE memory_jobs SET execution_identity_hash=:hash WHERE id=:id"),
            {"id": job.id, "hash": "g" * 64},
        )
        await f.session.commit()
    await f.session.rollback()
    for source in [*turns, item, state, f.policy, f.campaign]:
        await f.session.refresh(source)

    legacy = new_job(f, turns, item, state, key="9" * 64)
    legacy.manifest_hash = "e" * 64
    legacy.prompt_version = "legacy-prompt"
    f.session.add(legacy)
    await f.session.commit()
    with pytest.raises(IntegrityError):
        await f.session.execute(
            text(
                "UPDATE memory_jobs SET execution_identity=CAST(:identity AS jsonb), "
                "execution_identity_hash=:hash, execution_identity_version=1 WHERE id=:id"
            ),
            {
                "id": legacy.id,
                "identity": identity_json,
                "hash": identity_hash,
            },
        )
        await f.session.commit()
    await f.session.rollback()


async def test_manual_retry_is_nonterminal_and_definitive_terminal_time_is_once(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job, _, _, _ = await new_identity_job(f, turns, item, state)

    await f.session.execute(
        text(
            "UPDATE memory_jobs SET state='blocked', claim_token=NULL, lease_expires_at=NULL "
            "WHERE id=:id"
        ),
        {"id": job.id},
    )
    await f.session.commit()
    await f.session.execute(
        text("UPDATE memory_jobs SET state='manual_retry_required' WHERE id=:id"),
        {"id": job.id},
    )
    await f.session.commit()
    assert (
        await f.session.execute(
            text("SELECT state, terminal_at, terminal_reason FROM memory_jobs WHERE id=:id"),
            {"id": job.id},
        )
    ).one() == ("manual_retry_required", None, None)

    with pytest.raises(IntegrityError):
        await f.session.execute(
            text("UPDATE memory_jobs SET terminal_at=now() WHERE id=:id"), {"id": job.id}
        )
        await f.session.commit()
    await f.session.rollback()
    with pytest.raises(IntegrityError):
        await f.session.execute(
            text("UPDATE memory_jobs SET state='exhausted' WHERE id=:id"), {"id": job.id}
        )
        await f.session.commit()
    await f.session.rollback()

    terminal_at = datetime.now(UTC)
    await f.session.execute(
        text(
            "UPDATE memory_jobs SET state='exhausted', terminal_at=:terminal_at, "
            "terminal_reason='required_result_send_budget_exhausted' WHERE id=:id"
        ),
        {"id": job.id, "terminal_at": terminal_at},
    )
    await f.session.commit()
    assert (
        await f.session.execute(
            text("SELECT state, terminal_at, terminal_reason FROM memory_jobs WHERE id=:id"),
            {"id": job.id},
        )
    ).one() == ("exhausted", terminal_at, "required_result_send_budget_exhausted")

    for value in (None, terminal_at + timedelta(seconds=1)):
        with pytest.raises(IntegrityError):
            await f.session.execute(
                text("UPDATE memory_jobs SET terminal_at=:terminal_at WHERE id=:id"),
                {"id": job.id, "terminal_at": value},
            )
            await f.session.commit()
        await f.session.rollback()
    with pytest.raises(IntegrityError):
        await f.session.execute(
            text("UPDATE memory_jobs SET state='manual_retry_required' WHERE id=:id"),
            {"id": job.id},
        )
        await f.session.commit()
    await f.session.rollback()
    with pytest.raises(IntegrityError):
        await f.session.execute(
            text("UPDATE memory_jobs SET terminal_reason=NULL WHERE id=:id"), {"id": job.id}
        )
        await f.session.commit()
    await f.session.rollback()
