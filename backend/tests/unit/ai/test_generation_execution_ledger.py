import asyncio

import pytest

from app.ai.generation_contracts import (
    FormatMode,
    GenerationRequest,
    RawGenerationReceipt,
)
from app.ai.generation_errors import Adapter, SchemaModeUnsupportedBeforeIO
from app.ai.generation_execution import GenerationExecutionError, execute_generation
from app.ai.generation_execution_ledger import (
    GenerationRecoveryPolicy,
    InMemoryGenerationLedger,
    SendOutcome,
)
from app.ai.response_validation import ValidatedResponse
from tests.unit.ai.generation_execution_test_support import (
    FakeProvider,
    Payload,
    execution_identity,
    generation_request,
    message_content,
    validate_payload,
)


@pytest.mark.asyncio
async def test_received_receipt_is_recorded_before_second_send() -> None:
    base = generation_request()
    first = RawGenerationReceipt(text='{"value":"invalid"}', raw_candidate="full-first")

    class DurableLedger(InMemoryGenerationLedger):
        def __init__(self) -> None:
            super().__init__()
            self.records: list[SendOutcome] = []

        async def record(self, identity: str, role: str, outcome: SendOutcome) -> None:
            self.records.append(outcome)
            await super().record(identity, role, outcome)

    ledger = DurableLedger()

    class OrderedProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            self.calls += 1
            if self.calls == 2:
                assert ledger.records[0].receipt is first
                assert ledger.records[0].receipt.raw_candidate == "full-first"
            return first if self.calls == 1 else RawGenerationReceipt(text='{"value":5}')

    await execute_generation(
        base,
        OrderedProvider(),
        ledger,
        GenerationRecoveryPolicy(2),
        Adapter.OPENAI,
        validator=validate_payload,
    )


@pytest.mark.asyncio
async def test_record_failure_stops_before_another_send() -> None:
    base = generation_request()

    class FailingLedger(InMemoryGenerationLedger):
        async def record(self, identity: str, role: str, outcome: SendOutcome) -> None:
            raise OSError("ledger unavailable")

    provider = FakeProvider(
        [RawGenerationReceipt(text='{"value":"bad"}'), RawGenerationReceipt(text='{"value":3}')],
        [],
    )
    with pytest.raises(OSError, match="ledger unavailable"):
        await execute_generation(
            base,
            provider,
            FailingLedger(),
            GenerationRecoveryPolicy(3),
            Adapter.OPENAI,
            validator=validate_payload,
        )
    assert len(provider.requests) == 1


@pytest.mark.asyncio
async def test_cancellation_records_uncertain_reservation_and_propagates() -> None:
    base = generation_request()

    class CancelProvider:
        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            raise asyncio.CancelledError

    ledger = InMemoryGenerationLedger()
    with pytest.raises(asyncio.CancelledError):
        await execute_generation(
            base,
            CancelProvider(),
            ledger,
            GenerationRecoveryPolicy(3),
            Adapter.OPENAI,
            validator=validate_payload,
        )
    count = ledger.send_count(execution_identity(base), base.role)
    assert count == 1
    outcome = (await ledger.history(execution_identity(base), base.role))[0].outcome
    assert outcome is not None and outcome.status == "uncertain"


@pytest.mark.asyncio
async def test_cancellation_propagates_when_uncertain_record_write_fails() -> None:
    base = generation_request()

    class FailingRecordLedger(InMemoryGenerationLedger):
        def __init__(self) -> None:
            super().__init__()
            self.record_attempted = False

        async def record(self, identity: str, role: str, outcome: SendOutcome) -> None:
            self.record_attempted = True
            raise OSError("record store unavailable")

    class CancelProvider:
        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            raise asyncio.CancelledError

    ledger = FailingRecordLedger()
    with pytest.raises(asyncio.CancelledError):
        await execute_generation(
            base,
            CancelProvider(),
            ledger,
            GenerationRecoveryPolicy(3),
            Adapter.OPENAI,
            validator=validate_payload,
        )
    assert ledger.record_attempted
    assert ledger.send_count(execution_identity(base), base.role) == 1
    entries = await ledger.history(execution_identity(base), base.role)
    assert len(entries) == 1 and entries[0].outcome is None


@pytest.mark.asyncio
async def test_validator_bug_is_recorded_with_receipt_and_stops() -> None:
    base = generation_request()
    receipt = RawGenerationReceipt(text='{"value":1}', raw_candidate="complete")
    provider = FakeProvider([receipt, RawGenerationReceipt(text='{"value":2}')], [])
    ledger = InMemoryGenerationLedger()

    def broken_validator(
        actual: RawGenerationReceipt, derived: GenerationRequest
    ) -> ValidatedResponse[Payload]:
        raise TypeError("internal path details must not be stored")

    with pytest.raises(GenerationExecutionError, match="validation failed internally"):
        await execute_generation(
            base,
            provider,
            ledger,
            GenerationRecoveryPolicy(3),
            Adapter.OPENAI,
            validator=broken_validator,
        )
    assert len(provider.requests) == 1
    outcome = (await ledger.history(execution_identity(base), base.role))[0].outcome
    assert outcome is not None
    assert outcome.status == "internal_failure"
    assert outcome.receipt is receipt
    assert "internal path" not in repr(outcome)


@pytest.mark.asyncio
async def test_fallback_after_invalid_correction_preserves_history_and_prefix() -> None:
    base = generation_request(allow_json=True)

    class CorrectionFallbackProvider:
        def __init__(self) -> None:
            self.requests: list[GenerationRequest] = []

        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            self.requests.append(request)
            if len(self.requests) == 1:
                return RawGenerationReceipt(text='{"value":"failed-candidate"}')
            if len(self.requests) == 2:
                raise SchemaModeUnsupportedBeforeIO
            return RawGenerationReceipt(text='{"value":6}')

    provider = CorrectionFallbackProvider()
    ledger = InMemoryGenerationLedger()
    result = await execute_generation(
        base,
        provider,
        ledger,
        GenerationRecoveryPolicy(3),
        Adapter.OPENAI,
        validator=validate_payload,
    )
    assert result.value.value == 6
    assert len(provider.requests) == 3
    assert provider.requests[1].initial_prefix_hash != base.initial_prefix_hash
    assert provider.requests[2].format_mode is FormatMode.JSON_MODE
    assert provider.requests[2].initial_prefix_hash == provider.requests[1].initial_prefix_hash
    assert "failed-candidate" in message_content(provider.requests[2].messages[-2])
    assert ledger.send_count(execution_identity(base), base.role) == 3
