import asyncio
from dataclasses import replace

import pytest
from sqlalchemy import select

from app import dependencies
from app.ai.generation_contracts import (
    FormatMode,
    GenerationRequest,
    GenerationToolReceipt,
    OutputLimit,
    RawGenerationReceipt,
    RawToolArguments,
)
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
from app.ai.providers.usage import UsageMetadata
from app.ai.response_contracts import ResponseContract
from app.ai.response_validation import (
    DiagnosticCode,
    Normalization,
    ValidationDiagnostic,
)
from app.memory.generation_ledger import DurableMemoryGenerationLedger
from app.models.memory_generation import MemoryGeneration
from tests.integration.memory.generation_ledger_support import (
    LedgerPayload,
    create_ledger_fixture,
    validate_receipt,
)
from tests.integration.memory.storage_support import HistoryFixture


class NoSendProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def send(self, _request):
        self.calls += 1
        raise AssertionError("A valid durable candidate must replay without provider I/O.")


class InspectingProvider:
    def __init__(self, fixture) -> None:
        self.fixture = fixture
        self.calls = 0

    async def send(self, _request):
        self.calls += 1
        async with dependencies.async_session() as independent:
            stored = await independent.scalar(
                select(MemoryGeneration).where(
                    MemoryGeneration.job_id == self.fixture.job_id,
                    MemoryGeneration.send_number == 1,
                )
            )
            assert stored is not None and stored.status is None
            return RawGenerationReceipt(text='{"value":"sent-after-reservation"}')


async def test_executor_commits_reservation_before_provider_io(
    history_fixture: HistoryFixture,
) -> None:
    fixture = await create_ledger_fixture(history_fixture)
    provider = InspectingProvider(fixture)
    result = await execute_generation(
        fixture.request,
        provider,
        DurableMemoryGenerationLedger(fixture.claim),
        GenerationRecoveryPolicy(3),
        Adapter.LOCAL,
        validator=validate_receipt,
    )
    assert result.value.value == "sent-after-reservation"
    assert provider.calls == 1


async def test_reservation_commits_and_valid_typed_receipt_replays_from_fresh_ledger(
    history_fixture: HistoryFixture,
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
    async with dependencies.async_session() as independent:
        stored = await independent.scalar(
            select(MemoryGeneration).where(
                MemoryGeneration.job_id == fixture.job_id,
                MemoryGeneration.send_number == reservation.number,
            )
        )
        assert stored is not None and stored.status is None

    await ledger.record(
        fixture.identity,
        "summary",
        SendOutcome(
            reservation,
            GenerationOutcomeStatus.VALID,
            receipt=RawGenerationReceipt(text='{"value":"persisted"}'),
        ),
    )
    replay_ledger = DurableMemoryGenerationLedger(fixture.claim)
    history = await replay_ledger.history(fixture.identity, "summary")
    assert len(history) == 1
    assert history[0].outcome is not None
    assert history[0].outcome.receipt is not None
    assert history[0].outcome.receipt.text == '{"value":"persisted"}'

    provider = NoSendProvider()
    result = await execute_generation(
        fixture.request,
        provider,
        replay_ledger,
        GenerationRecoveryPolicy(3),
        Adapter.LOCAL,
        validator=validate_receipt,
    )

    assert result.value.value == "persisted"
    assert provider.calls == 0


async def test_ledger_rejects_wrong_role_source_cap_and_duplicate_outcome(
    history_fixture: HistoryFixture,
) -> None:
    fixture = await create_ledger_fixture(history_fixture)
    ledger = DurableMemoryGenerationLedger(fixture.claim)
    attempt = GenerationAttempt(
        fixture.request.identity.digest,
        fixture.request.identity.snapshot_json,
        fixture.request.format_mode,
        GenerationSendKind.INITIAL,
    )

    with pytest.raises(GenerationExecutionError):
        await ledger.reserve(fixture.identity, "facts", 3, attempt)
    with pytest.raises(GenerationExecutionError):
        await ledger.reserve(fixture.identity, "summary", 2, attempt)
    wrong_source = GenerationRequest.create(
        "Produce one value.",
        [{"role": "user", "content": "value"}],
        contract=ResponseContract("ledger_payload", "test-v1", LedgerPayload),
        provider="other-provider",
        model="test-model",
        destination_fingerprint="destination-v1",
        role="summary",
        logical_result_id=f"{fixture.job_id}:summary",
        output_limit=OutputLimit(configured_ceiling=512),
        contextual_validator_version="memory-context-summary-v1",
    )
    with pytest.raises(GenerationExecutionError):
        await ledger.reserve(
            fixture.identity,
            "summary",
            3,
            GenerationAttempt(
                wrong_source.identity.digest,
                wrong_source.identity.snapshot_json,
                wrong_source.format_mode,
                GenerationSendKind.INITIAL,
            ),
        )

    reservation = await ledger.reserve(fixture.identity, "summary", 3, attempt)
    outcome = SendOutcome(
        reservation,
        GenerationOutcomeStatus.VALID,
        receipt=RawGenerationReceipt(text='{"value":"once"}'),
    )
    await ledger.record(fixture.identity, "summary", outcome)
    with pytest.raises(GenerationExecutionError):
        await ledger.record(fixture.identity, "summary", outcome)


async def test_roles_have_independent_consecutive_budgets_and_parallel_final_slot(
    history_fixture: HistoryFixture,
) -> None:
    fixture = await create_ledger_fixture(history_fixture, roles=("summary", "facts"))
    ledger = DurableMemoryGenerationLedger(fixture.claim)
    summary = fixture.requests["summary"]
    summary_attempt = GenerationAttempt(
        summary.identity.digest,
        summary.identity.snapshot_json,
        summary.format_mode,
        GenerationSendKind.INITIAL,
    )
    facts = fixture.requests["facts"]
    facts_attempt = GenerationAttempt(
        facts.identity.digest,
        facts.identity.snapshot_json,
        facts.format_mode,
        GenerationSendKind.INITIAL,
    )
    first_summary = await ledger.reserve(
        fixture.identities["summary"], "summary", 3, summary_attempt
    )
    first_facts = await ledger.reserve(fixture.identities["facts"], "facts", 3, facts_attempt)
    assert first_summary.number == first_facts.number == 1
    second_summary = await ledger.reserve(
        fixture.identities["summary"], "summary", 3, summary_attempt
    )
    assert second_summary.number == 2

    concurrent = await asyncio.gather(
        ledger.reserve(fixture.identities["summary"], "summary", 3, summary_attempt),
        ledger.reserve(fixture.identities["summary"], "summary", 3, summary_attempt),
        return_exceptions=True,
    )
    assert sum(not isinstance(result, Exception) for result in concurrent) == 1
    assert sum(isinstance(result, GenerationExecutionError) for result in concurrent) == 1


async def test_receipt_tool_bytes_usage_and_safe_outcome_metadata_round_trip(
    history_fixture: HistoryFixture,
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
    receipt = RawGenerationReceipt(
        text='{"wrong":"payload"}',
        tool_calls=(
            GenerationToolReceipt(
                "call-1",
                "structured",
                RawToolArguments.structured({"nested": [1, True]}),
                b"\x00\xff",
            ),
            GenerationToolReceipt(
                "call-2", "raw", RawToolArguments.raw_text('{"not parsed": true}'), None
            ),
        ),
        usage=UsageMetadata(input_tokens=13, output_tokens=7, cost=0.125, response_id="resp"),
        raw_candidate='{"wrong":"payload"}',
    )
    diagnostic = ValidationDiagnostic(DiagnosticCode.MISSING, ("value",))
    await ledger.record(
        fixture.identity,
        "summary",
        SendOutcome(
            reservation,
            GenerationOutcomeStatus.INVALID,
            receipt=receipt,
            reason="validation_failed",
            diagnostics=(diagnostic,),
            normalization=Normalization.JSON_FENCE_V1,
        ),
    )

    outcome = (
        await DurableMemoryGenerationLedger(fixture.claim).history(fixture.identity, "summary")
    )[0].outcome
    assert outcome is not None
    assert outcome.reason == "validation_failed"
    assert outcome.diagnostics == (diagnostic,)
    assert outcome.normalization is Normalization.JSON_FENCE_V1
    assert outcome.receipt == receipt


async def test_record_rejects_reservation_with_mismatched_format_mode(
    history_fixture: HistoryFixture,
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
    mismatched = replace(
        reservation,
        attempt=replace(reservation.attempt, format_mode=FormatMode.JSON_MODE),
    )
    with pytest.raises(GenerationExecutionError):
        await ledger.record(
            fixture.identity,
            "summary",
            SendOutcome(
                mismatched,
                GenerationOutcomeStatus.VALID,
                receipt=RawGenerationReceipt(text='{"value":"wrong-mode"}'),
            ),
        )
    history = await ledger.history(fixture.identity, "summary")
    assert len(history) == 1 and history[0].outcome is None
    await ledger.record(
        fixture.identity,
        "summary",
        SendOutcome(
            reservation,
            GenerationOutcomeStatus.VALID,
            receipt=RawGenerationReceipt(text='{"value":"correct-mode"}'),
        ),
    )
    assert (await ledger.history(fixture.identity, "summary"))[0].outcome is not None
