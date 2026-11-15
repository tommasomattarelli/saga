import asyncio

import httpx
import pytest
from sqlalchemy import select

from app import dependencies
from app.ai.generation_contracts import FormatMode, RawGenerationReceipt
from app.ai.generation_errors import Adapter
from app.ai.generation_execution import execute_generation
from app.ai.generation_execution_ledger import (
    GenerationAttempt,
    GenerationExecutionError,
    GenerationOutcomeStatus,
    GenerationRecoveryPolicy,
    GenerationSendKind,
    SendOutcome,
)
from app.memory.generation_ledger import DurableMemoryGenerationLedger
from app.memory.job_claims import claim_job, fail_claim, retry_job
from app.memory.job_contracts import MemoryGenerationRequestIdentitySnapshot
from app.models.memory_generation import MemoryGeneration
from tests.integration.memory.generation_ledger_support import (
    create_ledger_fixture,
    validate_receipt,
)
from tests.integration.memory.storage_support import HistoryFixture


class CorrectionProvider:
    def __init__(self, job_id) -> None:
        self.job_id = job_id
        self.calls = 0

    async def send(self, request):
        self.calls += 1
        if self.calls == 1:
            return RawGenerationReceipt(text='{"wrong":"candidate"}')
        async with dependencies.async_session() as db:
            sends = list(
                await db.scalars(
                    select(MemoryGeneration)
                    .where(MemoryGeneration.job_id == self.job_id)
                    .order_by(MemoryGeneration.send_number)
                )
            )
            assert len(sends) == 2
            assert sends[0].status == "invalid"
            assert sends[0].receipt is not None
        current = MemoryGenerationRequestIdentitySnapshot.model_validate_json(
            sends[1].request_identity_snapshot
        )
        assert current.snapshot_json == request.identity.snapshot_json
        assert current.digest == request.identity.digest
        return RawGenerationReceipt(text='{"value":"corrected"}')


class ModeProvider:
    async def send(self, request):
        assert request.format_mode is FormatMode.JSON_MODE
        return RawGenerationReceipt(text='{"value":"fallback"}')


class RetryProvider:
    async def send(self, request):
        assert request.identity.digest != ""
        return RawGenerationReceipt(text='{"value":"retried"}')


class CancelProvider:
    async def send(self, _request):
        raise asyncio.CancelledError


class TransportRetryProvider:
    def __init__(self, job_id) -> None:
        self.job_id = job_id
        self.calls = 0

    async def send(self, _request):
        self.calls += 1
        if self.calls == 1:
            raise httpx.ConnectError("offline")
        async with dependencies.async_session() as db:
            rows = list(
                await db.scalars(
                    select(MemoryGeneration)
                    .where(MemoryGeneration.job_id == self.job_id)
                    .order_by(MemoryGeneration.send_number)
                )
            )
            assert len(rows) == 2
            assert rows[0].status == "retry"
            assert rows[0].outcome_reason == "transport_failure"
        return RawGenerationReceipt(text='{"value":"network-recovered"}')


async def test_invalid_candidate_is_committed_before_real_executor_correction(
    history_fixture: HistoryFixture,
) -> None:
    fixture = await create_ledger_fixture(history_fixture)
    provider = CorrectionProvider(fixture.job_id)
    result = await execute_generation(
        fixture.request,
        provider,
        DurableMemoryGenerationLedger(fixture.claim),
        GenerationRecoveryPolicy(3),
        Adapter.LOCAL,
        validator=validate_receipt,
    )

    assert result.value.value == "corrected"
    assert [outcome.status.value for outcome in result.sends] == ["invalid", "valid"]
    assert provider.calls == 2


@pytest.mark.parametrize("uncertain", [False, True])
async def test_pending_or_uncertain_reservation_is_counted_and_never_replayed(
    history_fixture: HistoryFixture, uncertain: bool
) -> None:
    fixture = await create_ledger_fixture(history_fixture)
    ledger = DurableMemoryGenerationLedger(fixture.claim)
    attempt = GenerationAttempt(
        fixture.request.identity.digest,
        fixture.request.identity.snapshot_json,
        fixture.request.format_mode,
        GenerationSendKind.INITIAL,
    )
    reservation = await ledger.reserve(fixture.identity, "summary", 3, attempt)
    if uncertain:
        await ledger.record(
            fixture.identity,
            "summary",
            SendOutcome(reservation, GenerationOutcomeStatus.UNCERTAIN, reason="cancelled"),
        )

    provider = CorrectionProvider(fixture.job_id)
    with pytest.raises(GenerationExecutionError):
        await execute_generation(
            fixture.request,
            provider,
            DurableMemoryGenerationLedger(fixture.claim),
            GenerationRecoveryPolicy(3),
            Adapter.LOCAL,
            validator=validate_receipt,
        )
    assert provider.calls == 0


@pytest.mark.parametrize(
    ("status", "reason", "fallback"),
    [
        (GenerationOutcomeStatus.SCHEMA_MODE_UNSUPPORTED, "schema_mode_unsupported", True),
        (GenerationOutcomeStatus.RETRY, "timeout", False),
    ],
)
async def test_fallback_and_transport_history_reconstructs_through_executor(
    history_fixture: HistoryFixture,
    status: GenerationOutcomeStatus,
    reason: str,
    fallback: bool,
) -> None:
    fixture = await create_ledger_fixture(history_fixture, allow_json_mode_fallback=fallback)
    ledger = DurableMemoryGenerationLedger(fixture.claim)
    attempt = GenerationAttempt(
        fixture.request.identity.digest,
        fixture.request.identity.snapshot_json,
        fixture.request.format_mode,
        GenerationSendKind.INITIAL,
    )
    reservation = await ledger.reserve(fixture.identity, "summary", 3, attempt)
    await ledger.record(
        fixture.identity,
        "summary",
        SendOutcome(reservation, status, reason=reason),
    )
    provider = ModeProvider() if fallback else RetryProvider()
    result = await execute_generation(
        fixture.request,
        provider,
        DurableMemoryGenerationLedger(fixture.claim),
        GenerationRecoveryPolicy(3),
        Adapter.LOCAL,
        validator=validate_receipt,
    )

    assert result.value.value == ("fallback" if fallback else "retried")
    history = await ledger.history(fixture.identity, "summary")
    assert history[1].reservation.attempt.send_kind is (
        GenerationSendKind.FALLBACK if fallback else GenerationSendKind.TRANSPORT_RETRY
    )


async def test_executor_cancellation_records_uncertain_and_keeps_reservation_counted(
    history_fixture: HistoryFixture,
) -> None:
    fixture = await create_ledger_fixture(history_fixture)
    with pytest.raises(asyncio.CancelledError):
        await execute_generation(
            fixture.request,
            CancelProvider(),
            DurableMemoryGenerationLedger(fixture.claim),
            GenerationRecoveryPolicy(3),
            Adapter.LOCAL,
            validator=validate_receipt,
        )
    history = await DurableMemoryGenerationLedger(fixture.claim).history(
        fixture.identity, "summary"
    )
    assert len(history) == 1
    assert history[0].outcome is not None
    assert history[0].outcome.status is GenerationOutcomeStatus.UNCERTAIN


async def test_real_network_failure_reason_persists_before_executor_retries(
    history_fixture: HistoryFixture,
) -> None:
    fixture = await create_ledger_fixture(history_fixture)
    provider = TransportRetryProvider(fixture.job_id)
    result = await execute_generation(
        fixture.request,
        provider,
        DurableMemoryGenerationLedger(fixture.claim),
        GenerationRecoveryPolicy(3),
        Adapter.LOCAL,
        validator=validate_receipt,
    )
    assert result.value.value == "network-recovered"
    assert provider.calls == 2
    history = await DurableMemoryGenerationLedger(fixture.claim).history(
        fixture.identity, "summary"
    )
    assert history[0].outcome is not None
    assert history[0].outcome.reason == "transport_failure"
    assert history[1].reservation.attempt.send_kind is GenerationSendKind.TRANSPORT_RETRY


async def test_successful_candidate_replays_under_a_new_real_job_claim(
    history_fixture: HistoryFixture,
) -> None:
    fixture = await create_ledger_fixture(history_fixture)
    first_provider = CorrectionProvider(fixture.job_id)
    first_result = await execute_generation(
        fixture.request,
        first_provider,
        DurableMemoryGenerationLedger(fixture.claim),
        GenerationRecoveryPolicy(3),
        Adapter.LOCAL,
        validator=validate_receipt,
    )
    assert first_result.value.value == "corrected"
    old_claim_ledger = DurableMemoryGenerationLedger(fixture.claim)
    async with dependencies.async_session() as db:
        assert await fail_claim(db, fixture.claim, configuration_required=True)
        await db.commit()
        assert await retry_job(db, fixture.claim.campaign_id, fixture.claim.job_id)
        await db.commit()
        second_claim = await claim_job(db, fixture.claim.campaign_id, fixture.claim.job_id)
        assert second_claim is not None
        await db.commit()

    assert second_claim.token != fixture.claim.token
    assert second_claim.attempt_id != fixture.claim.attempt_id
    second_provider = CorrectionProvider(fixture.job_id)
    second_result = await execute_generation(
        fixture.request,
        second_provider,
        DurableMemoryGenerationLedger(second_claim),
        GenerationRecoveryPolicy(3),
        Adapter.LOCAL,
        validator=validate_receipt,
    )
    assert second_result.value.value == "corrected"
    assert second_provider.calls == 0

    with pytest.raises(GenerationExecutionError):
        await old_claim_ledger.record(fixture.identity, "summary", first_result.sends[0])
    with pytest.raises(GenerationExecutionError):
        await old_claim_ledger.reserve(
            fixture.identity,
            "summary",
            3,
            GenerationAttempt(
                fixture.request.identity.digest,
                fixture.request.identity.snapshot_json,
                fixture.request.format_mode,
                GenerationSendKind.INITIAL,
            ),
        )
