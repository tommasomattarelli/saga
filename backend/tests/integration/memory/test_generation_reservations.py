from uuid import uuid4

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError

from app.ai.generation_contracts import FormatMode
from app.models.memory_generation import MemoryGeneration
from tests.integration.memory.job_support import job_sources, new_attempt, new_identity_job
from tests.integration.memory.storage_support import HistoryFixture


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "rewritten"),
        ("model", "rewritten"),
        ("role", "facts"),
        ("send_number", 2),
        ("send_kind", "fallback"),
        ("request_identity_hash", "0" * 64),
        ("format_mode", FormatMode.JSON_MODE),
        ("attempt_id", uuid4()),
    ],
)
async def test_reservation_identity_and_original_claim_association_are_immutable(
    history_fixture: HistoryFixture, field: str, value: object
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
    if field == "attempt_id":
        replacement_attempt = new_attempt(job, 2)
        replacement_attempt.state = "started"
        replacement_attempt.finished_at = None
        replacement_attempt.error = None
        replacement_attempt.retry_cycle = 0
        replacement_attempt.claim_token = attempt.claim_token
        f.session.add(replacement_attempt)
        await f.session.commit()
        value = replacement_attempt.id
    with pytest.raises(IntegrityError):
        await f.session.execute(
            update(MemoryGeneration)
            .where(MemoryGeneration.id == generation.id)
            .values(**{field: value})
        )
        await f.session.commit()
    await f.session.rollback()


async def test_reservations_use_the_job_identity_send_limit(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job, attempt, _, request_identity_hash = await new_identity_job(f, turns, item, state)

    for send_number in range(1, 6):
        f.session.add(
            MemoryGeneration(
                id=uuid4(),
                job_id=job.id,
                attempt_id=attempt.id,
                campaign_id=job.campaign_id,
                policy_id=job.policy_id,
                batch_id=job.batch_id,
                role="summary",
                provider="local",
                model="test-model",
                send_number=send_number,
                send_kind="initial" if send_number == 1 else "correction",
                request_identity_hash=request_identity_hash,
                format_mode=FormatMode.STRICT_NATIVE,
            )
        )
    await f.session.commit()

    f.session.add(
        MemoryGeneration(
            id=uuid4(),
            job_id=job.id,
            attempt_id=attempt.id,
            campaign_id=job.campaign_id,
            policy_id=job.policy_id,
            batch_id=job.batch_id,
            role="summary",
            provider="local",
            model="test-model",
            send_number=6,
            send_kind="correction",
            request_identity_hash=request_identity_hash,
            format_mode=FormatMode.STRICT_NATIVE,
        )
    )
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()

    facts_hash = await f.session.scalar(
        text(
            "SELECT execution_identity->'result_identities'->'facts'->>'request_identity_hash' "
            "FROM memory_jobs WHERE id=:id"
        ),
        {"id": job.id},
    )
    assert facts_hash is not None
    for send_number in range(1, 6):
        f.session.add(
            MemoryGeneration(
                id=uuid4(),
                job_id=job.id,
                attempt_id=attempt.id,
                campaign_id=job.campaign_id,
                policy_id=job.policy_id,
                batch_id=job.batch_id,
                role="facts",
                provider="local",
                model="test-model",
                send_number=send_number,
                send_kind="initial" if send_number == 1 else "correction",
                request_identity_hash=facts_hash,
                format_mode=FormatMode.STRICT_NATIVE,
            )
        )
    await f.session.commit()
    f.session.add(
        MemoryGeneration(
            id=uuid4(),
            job_id=job.id,
            attempt_id=attempt.id,
            campaign_id=job.campaign_id,
            policy_id=job.policy_id,
            batch_id=job.batch_id,
            role="facts",
            provider="local",
            model="test-model",
            send_number=6,
            send_kind="correction",
            request_identity_hash=facts_hash,
            format_mode=FormatMode.STRICT_NATIVE,
        )
    )
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()
