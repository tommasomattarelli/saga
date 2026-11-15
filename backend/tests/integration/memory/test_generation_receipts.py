import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError

from app.ai.generation_contracts import (
    GenerationToolReceipt,
    RawGenerationReceipt,
    RawToolArguments,
)
from app.ai.generation_errors import (
    _ROUTER_RETRY_TYPES,
    _ROUTER_TERMINAL,
    Adapter,
    FailureSignals,
    classify_failure,
)
from app.ai.providers.usage import UsageMetadata
from app.memory.generation_receipts import decode_receipt, encode_receipt
from app.memory.job_retention import cleanup_terminal_generation_payloads
from app.models.memory_generation import MemoryGeneration
from tests.integration.memory.job_support import job_sources, new_identity_job, send_identity
from tests.integration.memory.storage_support import HistoryFixture


def _classifier_reason_codes() -> tuple[str, ...]:
    cases = [
        FailureSignals(Adapter.LOCAL),
        FailureSignals(Adapter.LOCAL, exception=asyncio.CancelledError()),
        FailureSignals(Adapter.LOCAL, exception=RuntimeError()),
        FailureSignals(
            Adapter.LOCAL, exception=RuntimeError(), pre_io_schema_incompatibility=True
        ),
        FailureSignals(Adapter.LOCAL, pre_io_schema_incompatibility=True),
        FailureSignals(Adapter.LOCAL, refusal=True),
        FailureSignals(Adapter.LOCAL, context_length_exceeded=True),
        FailureSignals(Adapter.LOCAL, finish_reason="LENGTH"),
        FailureSignals(Adapter.LOCAL, prompt_blocked=True),
        FailureSignals(Adapter.OPENAI, http_status=429, code="insufficient_quota"),
        FailureSignals(Adapter.OPENAI, http_status=429, code="rate_limit_exceeded"),
        FailureSignals(Adapter.OPENAI, http_status=429),
        FailureSignals(Adapter.OPENAI, http_status=503),
        FailureSignals(Adapter.GOOGLE, status="INVALID_ARGUMENT"),
        FailureSignals(Adapter.GOOGLE, http_status=429, status="RESOURCE_EXHAUSTED"),
        FailureSignals(Adapter.GOOGLE, http_status=500),
        FailureSignals(Adapter.OPENROUTER, http_status=429),
        FailureSignals(Adapter.OPENROUTER, http_status=408),
    ]
    cases.extend(
        FailureSignals(Adapter.OPENROUTER, error_type=error_type)
        for error_type in (
            *_ROUTER_RETRY_TYPES,
            *_ROUTER_TERMINAL,
            "rate_limit_exceeded",
            "unknown",
        )
    )
    return tuple(
        sorted(
            {classify_failure(signals).reason for signals in cases}
            | {"validation_failed", "validator_failure"}
        )
    )


@pytest.mark.parametrize("reason", _classifier_reason_codes())
async def test_every_current_classifier_reason_is_persistable(
    history_fixture: HistoryFixture, reason: str
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job, attempt, _, _ = await new_identity_job(f, turns, item, state)
    assert job.execution_identity is not None
    request_hash, request_snapshot = send_identity(job, "summary")
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
        send_kind="initial",
        request_identity_hash=request_hash,
        request_identity_snapshot=request_snapshot,
        format_mode=job.execution_identity.result_identities["summary"].format_mode,
    )
    f.session.add(generation)
    await f.session.commit()
    generation.status = "invalid"
    generation.outcome_reason = reason
    await f.session.commit()


async def test_outcome_reason_rejects_untrusted_payload_text(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job, attempt, _, _ = await new_identity_job(f, turns, item, state)
    assert job.execution_identity is not None
    request_hash, request_snapshot = send_identity(job, "summary")
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
        send_kind="initial",
        request_identity_hash=request_hash,
        request_identity_snapshot=request_snapshot,
        format_mode=job.execution_identity.result_identities["summary"].format_mode,
    )
    f.session.add(generation)
    await f.session.commit()
    generation.status = "invalid"
    generation.outcome_reason = "RuntimeError: private details"
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()


async def test_receipt_envelope_and_candidate_round_trip_in_postgres(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    campaign_id = f.campaign.id
    turns, item, state = await job_sources(f)
    job, attempt, _, _ = await new_identity_job(f, turns, item, state)
    assert job.execution_identity is not None
    request_identity_hash, request_identity_snapshot = send_identity(job, "summary")
    candidate = '{"value": "candidate"}'
    receipt = RawGenerationReceipt(
        text="visible text",
        tool_calls=(
            GenerationToolReceipt(
                "tool-call",
                "tool",
                RawToolArguments.raw_text("{ malformed"),
                b"opaque",
            ),
        ),
        finish_reason="stop",
        response_id="response-id",
        model_id="model-id",
        usage=UsageMetadata(input_tokens=11, output_tokens=13, total_tokens=24),
        text_signature=b"text-signature",
        raw_candidate=candidate,
    )
    envelope, stored_candidate = encode_receipt(receipt)
    row = MemoryGeneration(
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
        format_mode=job.execution_identity.result_identities["summary"].format_mode,
    )
    f.session.add(row)
    await f.session.commit()
    row.status = "invalid"
    row.outcome_reason = "validation_failed"
    row.raw_candidate = stored_candidate
    row.raw_candidate_hash = hashlib.sha256(candidate.encode()).hexdigest()
    row.receipt = envelope
    await f.session.commit()
    await f.session.refresh(row)

    assert row.raw_candidate == candidate
    assert row.outcome_reason == "validation_failed"
    assert decode_receipt(row.receipt, row.raw_candidate) == receipt
    retained_hash = row.raw_candidate_hash
    receipt_evidence = await f.session.scalar(
        text(
            "SELECT EXISTS (SELECT 1 FROM memory_generations WHERE id=:id AND receipt IS NOT NULL)"
        ),
        {"id": row.id},
    )
    assert receipt_evidence is True

    second = MemoryGeneration(
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
        send_kind="transport_retry",
        request_identity_hash=request_identity_hash,
        request_identity_snapshot=request_identity_snapshot,
        format_mode=job.execution_identity.result_identities["summary"].format_mode,
    )
    f.session.add(second)
    await f.session.commit()
    second.status = "invalid"
    second.outcome_reason = "provider_request_rejected"
    await f.session.commit()
    await f.session.refresh(second)
    assert second.status == row.status
    assert second.outcome_reason == "provider_request_rejected"
    with pytest.raises(IntegrityError):
        await f.session.execute(
            update(MemoryGeneration)
            .where(MemoryGeneration.id == second.id)
            .values(outcome_reason="validation_failed")
        )
        await f.session.commit()
    await f.session.rollback()

    await f.session.execute(
        text(
            "UPDATE memory_jobs SET state = 'succeeded', claim_token = NULL, "
            "lease_expires_at = NULL, terminal_at = :terminal_at WHERE id = :id"
        ),
        {"terminal_at": datetime.now(UTC) - timedelta(days=2), "id": job.id},
    )
    await f.session.commit()
    assert (
        await cleanup_terminal_generation_payloads(f.session, campaign_id, retention_days=1) == 1
    )
    await f.session.commit()
    await f.session.refresh(row)
    assert row.raw_candidate is None
    assert row.receipt is None
    assert row.raw_candidate_hash == retained_hash
    assert row.outcome_reason == "validation_failed"


@pytest.mark.parametrize("payload_shape", ["candidate-only", "receipt-only"])
async def test_terminal_cleanup_clears_legacy_partial_payloads(
    history_fixture: HistoryFixture, payload_shape: str
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job, attempt, _, _ = await new_identity_job(f, turns, item, state)
    assert job.execution_identity is not None
    identity_hash, identity_snapshot = send_identity(job, "summary")
    candidate = '{"value": "candidate"}'
    raw_receipt = RawGenerationReceipt(
        text="visible text",
        usage=UsageMetadata(input_tokens=11, output_tokens=13, total_tokens=24),
        raw_candidate=candidate if payload_shape == "candidate-only" else None,
    )
    receipt, stored_candidate = encode_receipt(raw_receipt)
    row = MemoryGeneration(
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
        request_identity_hash=identity_hash,
        request_identity_snapshot=identity_snapshot,
        format_mode=job.execution_identity.result_identities["summary"].format_mode,
    )
    f.session.add(row)
    await f.session.commit()
    row.status = "invalid"
    row.outcome_reason = "validation_failed"
    row.raw_candidate = stored_candidate
    row.raw_candidate_hash = (
        hashlib.sha256(candidate.encode()).hexdigest() if stored_candidate is not None else None
    )
    row.receipt = receipt if payload_shape == "receipt-only" else None
    row.diagnostics = [["validator", "rejected"]]
    row.input_tokens = 11
    row.output_tokens = 13
    await f.session.commit()

    assert (row.raw_candidate is not None) == (payload_shape == "candidate-only")
    assert (row.receipt is not None) == (payload_shape == "receipt-only")
    terminal_at = datetime.now(UTC) - timedelta(days=2)
    await f.session.execute(
        text(
            "UPDATE memory_jobs SET state = 'succeeded', claim_token = NULL, "
            "lease_expires_at = NULL, terminal_at = :terminal_at WHERE id = :id"
        ),
        {"terminal_at": terminal_at, "id": job.id},
    )
    await f.session.commit()
    campaign_id = f.campaign.id
    terminal = await f.session.execute(
        text(
            "SELECT j.state, j.terminal_at <= clock_timestamp() - interval '1 day', "
            "g.raw_candidate IS NOT NULL, g.receipt IS NOT NULL "
            "FROM memory_jobs j JOIN memory_generations g ON g.job_id = j.id WHERE g.id = :id"
        ),
        {"id": row.id},
    )
    assert terminal.one() == (
        "succeeded",
        True,
        payload_shape == "candidate-only",
        payload_shape == "receipt-only",
    )

    assert (
        await cleanup_terminal_generation_payloads(f.session, campaign_id, retention_days=1) == 1
    )
    await f.session.commit()
    await f.session.refresh(row)
    assert row.raw_candidate is None
    assert row.receipt is None
    assert row.raw_candidate_hash == (
        hashlib.sha256(candidate.encode()).hexdigest()
        if payload_shape == "candidate-only"
        else None
    )
    assert row.status == "invalid"
    assert row.outcome_reason == "validation_failed"
    assert row.diagnostics == [["validator", "rejected"]]
    assert (row.input_tokens, row.output_tokens) == (11, 13)
    assert row.request_identity_hash == identity_hash
    assert row.request_identity_snapshot == identity_snapshot
    assert row.send_number == 1
    assert row.send_kind == "initial"
    assert (
        await cleanup_terminal_generation_payloads(f.session, f.campaign.id, retention_days=1) == 0
    )
