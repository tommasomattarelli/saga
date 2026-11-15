import hashlib
import json
from uuid import uuid4

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError

from app.ai.generation_contracts import FormatMode
from app.memory.job_contracts import MemoryGenerationRequestIdentitySnapshot
from app.models.memory_generation import MemoryGeneration
from tests.integration.memory.job_support import (
    job_sources,
    new_attempt,
    new_identity_job,
    send_identity,
)
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
    request_identity_hash, request_identity_snapshot = send_identity(job, "summary")
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
        request_identity_snapshot=request_identity_snapshot,
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
    request_identity_hash, request_identity_snapshot = send_identity(job, "summary")

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
                request_identity_snapshot=request_identity_snapshot,
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
            request_identity_snapshot=request_identity_snapshot,
            format_mode=FormatMode.STRICT_NATIVE,
        )
    )
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()


async def test_correction_reservation_binds_derived_hash_and_preserves_base_identity(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job, attempt, _, _ = await new_identity_job(
        f, turns, item, state, allow_json_mode_fallback=True
    )
    assert job.execution_identity is not None
    base = job.execution_identity.result_identities["summary"]
    snapshot = base.model_dump(mode="json", exclude={"request_identity_hash"})
    snapshot.update({"initial_prefix_hash": "f" * 64, "format_mode": FormatMode.JSON_MODE.value})
    derived = MemoryGenerationRequestIdentitySnapshot.model_validate_json(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    )
    assert derived.digest != base.request_identity_hash
    generation = MemoryGeneration(
        id=uuid4(),
        job_id=job.id,
        attempt_id=attempt.id,
        campaign_id=job.campaign_id,
        policy_id=job.policy_id,
        batch_id=job.batch_id,
        role="summary",
        provider="local",
        model="test-model",
        send_number=1,
        send_kind="correction",
        request_identity_hash=derived.digest,
        request_identity_snapshot=derived.snapshot_json,
        format_mode=FormatMode.JSON_MODE,
    )
    f.session.add(generation)
    await f.session.commit()

    assert job.execution_identity is not None
    assert generation.request_identity_hash == derived.digest
    assert job.execution_identity.result_identities["summary"].request_identity_hash == (
        base.request_identity_hash
    )


async def test_orm_rejects_column_format_that_differs_from_snapshot(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job, attempt, _, _ = await new_identity_job(f, turns, item, state)
    request_hash, snapshot = send_identity(job, "summary")
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
            send_number=1,
            send_kind="initial",
            request_identity_hash=request_hash,
            request_identity_snapshot=snapshot,
            format_mode=FormatMode.JSON_MODE,
        )
    )

    with pytest.raises(ValueError, match="identity"):
        await f.session.flush()
    await f.session.rollback()


@pytest.mark.parametrize("case", ["format_mode", "noncanonical"])
async def test_sql_rejects_format_mismatch_and_noncanonical_send_snapshot(
    history_fixture: HistoryFixture, case: str
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job, attempt, _, _ = await new_identity_job(f, turns, item, state)
    request_hash, snapshot = send_identity(job, "summary")
    if case == "noncanonical":
        parsed = json.loads(snapshot)
        snapshot = json.dumps(parsed, ensure_ascii=False, indent=2)
        request_hash = hashlib.sha256(snapshot.encode()).hexdigest()
    sql_mode = "json_mode" if case == "format_mode" else "strict_native"

    with pytest.raises(IntegrityError):
        await f.session.execute(
            text(
                "INSERT INTO memory_generations "
                "(id, job_id, attempt_id, campaign_id, policy_id, batch_id, role, provider, "
                "model, send_number, send_kind, request_identity_hash, "
                "request_identity_snapshot, format_mode) "
                "VALUES (:id, :job, :attempt, :campaign, :policy, :batch, 'summary', "
                "'local', 'test-model', 1, 'initial', :hash, :snapshot, :mode)"
            ),
            {
                "id": uuid4(),
                "job": job.id,
                "attempt": attempt.id,
                "campaign": job.campaign_id,
                "policy": job.policy_id,
                "batch": job.batch_id,
                "hash": request_hash,
                "snapshot": snapshot,
                "mode": sql_mode,
            },
        )
        await f.session.commit()
    await f.session.rollback()


async def test_postgres_canonical_identity_serialization_matches_typed_python_snapshot(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job, _, _, _ = await new_identity_job(f, turns, item, state)
    assert job.execution_identity is not None
    base = job.execution_identity.result_identities["summary"]
    fields = base.model_dump(mode="json", exclude={"request_identity_hash"})
    fields["model"] = "mødel/β"
    fields["logical_result_id"] = "café/β"
    snapshot = MemoryGenerationRequestIdentitySnapshot.model_validate_json(
        json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )

    canonical = await f.session.scalar(
        text("SELECT saga_memory_generation_request_snapshot(CAST(:snapshot AS jsonb))"),
        {"snapshot": snapshot.snapshot_json},
    )

    assert canonical == snapshot.snapshot_json
