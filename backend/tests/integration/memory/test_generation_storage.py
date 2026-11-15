import hashlib
from uuid import uuid4

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError

from app.ai.generation_contracts import FormatMode
from app.models.memory_generation import MemoryGeneration
from tests.integration.memory.job_support import (
    job_sources,
    new_attempt,
    new_generation,
    new_identity_job,
    new_job,
)
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_batch_storage import batch


@pytest.mark.parametrize("case", ["mixed_attempt", "mixed_batch", "rewrite_provenance"])
async def test_generation_provenance_must_match_the_same_job(
    history_fixture: HistoryFixture, case: str
) -> None:
    f = history_fixture
    turns, first_batch, state = await job_sources(f)
    third = await f.turn(turns[-1])
    fourth = await f.turn(third)
    second_batch = await batch(f, [third, fourth], first_batch)
    first_job = new_job(f, turns, first_batch, state)
    second_job = new_job(f, [third, fourth], second_batch, state, key="9" * 64)
    first_attempt, second_attempt = new_attempt(first_job, 1), new_attempt(second_job, 1)
    f.session.add_all([first_job, second_job, first_attempt, second_attempt])
    await f.session.commit()
    produced = new_generation(first_job, first_attempt)
    f.session.add(produced)
    await f.session.commit()
    if case == "rewrite_provenance":
        with pytest.raises(IntegrityError):
            await f.session.execute(
                update(MemoryGeneration)
                .where(MemoryGeneration.id == produced.id)
                .values(provider="rewritten")
            )
            await f.session.commit()
    else:
        invalid = new_generation(first_job, first_attempt)
        if case == "mixed_attempt":
            invalid.attempt_id = second_attempt.id
        else:
            invalid.batch_id = second_batch.id
        f.session.add(invalid)
        with pytest.raises(IntegrityError):
            await f.session.commit()
    await f.session.rollback()


@pytest.mark.parametrize(
    "case",
    [
        "zero",
        "negative",
        "empty_kind",
        "batch_role",
        "missing_request_hash",
        "missing_format_mode",
        "invalid_request_hash",
        "wrong_request_hash",
        "status_payload",
        "candidate_payload",
        "candidate_hash_payload",
        "diagnostics_payload",
        "normalization_payload",
        "usage_payload",
    ],
)
async def test_typed_reservations_require_identity_and_positive_numbers(
    history_fixture: HistoryFixture, case: str
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job, attempt, _, request_identity_hash = await new_identity_job(f, turns, item, state)
    generation = MemoryGeneration(
        id=uuid4(),
        job_id=job.id,
        attempt_id=attempt.id,
        campaign_id=f.campaign.id,
        policy_id=job.policy_id,
        batch_id=job.batch_id,
        role="summary",
        provider="local",
        model="test-model",
        send_number=1,
        send_kind="initial",
        request_identity_hash=request_identity_hash,
        format_mode=FormatMode.STRICT_NATIVE,
    )
    if case == "zero":
        generation.send_number = 0
    elif case == "negative":
        generation.send_number = -1
    elif case == "empty_kind":
        generation.send_kind = ""
    elif case == "batch_role":
        generation.role = "batch"
    elif case == "missing_request_hash":
        generation.request_identity_hash = None
    elif case == "missing_format_mode":
        generation.format_mode = None
    elif case == "wrong_request_hash":
        generation.request_identity_hash = "0" * 64
    elif case == "status_payload":
        generation.status = "uncertain"
    elif case == "candidate_payload":
        generation.raw_candidate = "candidate"
        generation.raw_candidate_hash = hashlib.sha256(b"candidate").hexdigest()
    elif case == "candidate_hash_payload":
        generation.raw_candidate_hash = hashlib.sha256(b"candidate").hexdigest()
    elif case == "diagnostics_payload":
        generation.diagnostics = []
    elif case == "normalization_payload":
        generation.normalization = "none"
    elif case == "usage_payload":
        generation.input_tokens = 0
    else:
        generation.request_identity_hash = "g" * 64
    f.session.add(generation)
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()


async def test_reservation_insert_requires_the_active_claim_fence(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job, attempt, _, request_identity_hash = await new_identity_job(f, turns, item, state)
    await f.session.execute(
        text("UPDATE memory_jobs SET lease_expires_at=now() - interval '1 second' WHERE id=:id"),
        {"id": job.id},
    )
    await f.session.commit()

    f.session.add(
        MemoryGeneration(
            id=uuid4(),
            job_id=job.id,
            attempt_id=attempt.id,
            campaign_id=f.campaign.id,
            policy_id=job.policy_id,
            batch_id=job.batch_id,
            role="summary",
            provider="local",
            model="test-model",
            send_number=1,
            send_kind="initial",
            request_identity_hash=request_identity_hash,
            format_mode=FormatMode.STRICT_NATIVE,
        )
    )
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()
