import hashlib
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError

from app.ai.generation_contracts import FormatMode
from app.models.memory_generation import MemoryGeneration
from tests.integration.memory.job_support import job_sources, new_identity_job
from tests.integration.memory.storage_support import HistoryFixture


async def test_reservation_records_exact_malformed_candidate_once_and_keeps_uncertain_sends(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job, attempt, _, request_identity_hash = await new_identity_job(f, turns, item, state)
    malformed = '{"summary": "unfinished'
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
    f.session.add(generation)
    await f.session.commit()
    assert generation.status is None
    assert generation.raw_candidate is None
    assert generation.raw_candidate_hash is None
    assert generation.request_identity_hash == request_identity_hash
    assert generation.format_mode is FormatMode.STRICT_NATIVE

    candidate_hash = hashlib.sha256(malformed.encode()).hexdigest()
    await f.session.execute(
        update(MemoryGeneration)
        .where(MemoryGeneration.id == generation.id)
        .values(
            status="invalid",
            raw_candidate=malformed,
            raw_candidate_hash=candidate_hash,
            diagnostics=[["invalid_json", []]],
            normalization="json_fence_v1",
            input_tokens=13,
            output_tokens=0,
            latency_ms=31,
        )
    )
    await f.session.commit()
    recorded = await f.session.get(MemoryGeneration, generation.id)
    assert recorded is not None
    await f.session.refresh(recorded)
    assert (
        recorded.status,
        recorded.raw_candidate,
        recorded.raw_candidate_hash,
        recorded.diagnostics,
        recorded.normalization,
        recorded.request_identity_hash,
        recorded.format_mode,
        recorded.input_tokens,
        recorded.output_tokens,
        recorded.latency_ms,
    ) == (
        "invalid",
        malformed,
        candidate_hash,
        [["invalid_json", []]],
        "json_fence_v1",
        request_identity_hash,
        FormatMode.STRICT_NATIVE,
        13,
        0,
        31,
    )

    uncertain = MemoryGeneration(
        id=uuid4(),
        job_id=job.id,
        attempt_id=attempt.id,
        campaign_id=f.campaign.id,
        policy_id=job.policy_id,
        batch_id=job.batch_id,
        role="summary",
        provider="local",
        model="test-model",
        send_number=2,
        send_kind="correction",
        request_identity_hash=request_identity_hash,
        format_mode=FormatMode.STRICT_NATIVE,
    )
    f.session.add(uncertain)
    await f.session.commit()
    await f.session.execute(
        update(MemoryGeneration)
        .where(MemoryGeneration.id == uncertain.id)
        .values(status="uncertain")
    )
    await f.session.commit()
    assert (
        await f.session.scalar(
            select(MemoryGeneration.send_number)
            .where(MemoryGeneration.job_id == job.id)
            .order_by(MemoryGeneration.send_number)
        )
        == 1
    )
    assert (
        await f.session.scalar(
            select(MemoryGeneration.send_number)
            .where(MemoryGeneration.job_id == job.id)
            .order_by(MemoryGeneration.send_number.desc())
        )
        == 2
    )

    empty_candidate = MemoryGeneration(
        id=uuid4(),
        job_id=job.id,
        attempt_id=attempt.id,
        campaign_id=f.campaign.id,
        policy_id=job.policy_id,
        batch_id=job.batch_id,
        role="summary",
        provider="local",
        model="test-model",
        send_number=3,
        send_kind="correction",
        request_identity_hash=request_identity_hash,
        format_mode=FormatMode.STRICT_NATIVE,
    )
    f.session.add(empty_candidate)
    await f.session.commit()
    empty_hash = hashlib.sha256(b"").hexdigest()
    await f.session.execute(
        update(MemoryGeneration)
        .where(MemoryGeneration.id == empty_candidate.id)
        .values(status="invalid", raw_candidate="", raw_candidate_hash=empty_hash)
    )
    await f.session.commit()
    reloaded_empty = await f.session.get(MemoryGeneration, empty_candidate.id)
    assert reloaded_empty is not None
    await f.session.refresh(reloaded_empty)
    assert reloaded_empty.raw_candidate == ""
    assert reloaded_empty.raw_candidate_hash == empty_hash

    duplicate = MemoryGeneration(
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
    f.session.add(duplicate)
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("raw_candidate", None),
        ("raw_candidate", '{"summary":"rewritten"}'),
        ("raw_candidate_hash", "0" * 64),
        ("status", "valid"),
        ("diagnostics", None),
        ("normalization", "json_fence_v1"),
        ("output_tokens", 1),
    ],
)
async def test_recorded_payload_and_outcome_cannot_be_cleared_or_rewritten(
    history_fixture: HistoryFixture, field: str, value: object
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job, attempt, _, request_identity_hash = await new_identity_job(f, turns, item, state)
    malformed = '{"summary": "unfinished'
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
    f.session.add(generation)
    await f.session.commit()
    await f.session.execute(
        update(MemoryGeneration)
        .where(MemoryGeneration.id == generation.id)
        .values(
            status="invalid",
            raw_candidate=malformed,
            raw_candidate_hash=hashlib.sha256(malformed.encode()).hexdigest(),
            diagnostics=[["invalid_json", []]],
            normalization="none",
        )
    )
    await f.session.execute(
        text(
            "UPDATE memory_jobs SET state='succeeded', claim_token=NULL, "
            "lease_expires_at=NULL, terminal_at=now() WHERE id=:id"
        ),
        {"id": job.id},
    )
    await f.session.commit()
    with pytest.raises(IntegrityError):
        await f.session.execute(
            update(MemoryGeneration)
            .where(MemoryGeneration.id == generation.id)
            .values(**{field: value})
        )
        await f.session.commit()
    await f.session.rollback()


async def test_raw_candidate_hash_must_match_candidate_contents(
    history_fixture: HistoryFixture,
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
    f.session.add(generation)
    await f.session.commit()
    with pytest.raises(IntegrityError):
        await f.session.execute(
            update(MemoryGeneration)
            .where(MemoryGeneration.id == generation.id)
            .values(status="invalid", raw_candidate="", raw_candidate_hash="0" * 64)
        )
        await f.session.commit()
    await f.session.rollback()
