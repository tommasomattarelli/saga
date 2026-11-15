import pytest

from app.ai.generation_contracts import GenerationRequest, RawGenerationReceipt
from app.ai.generation_errors import Adapter
from app.ai.generation_execution import execute_generation
from app.ai.generation_execution_ledger import (
    GenerationOutcomeStatus,
    GenerationRecoveryPolicy,
    InMemoryGenerationLedger,
    SendOutcome,
)
from app.ai.response_validation import ResponseValidationError, ValidatedResponse
from tests.unit.ai.generation_execution_test_support import (
    Payload,
    execution_identity,
    generation_request,
    message_content,
    validate_payload,
)


class SimulatedCrashError(Exception):
    pass


class CrashAfterRecordLedger(InMemoryGenerationLedger):
    def __init__(self, crash_status: str) -> None:
        super().__init__()
        self.crash_status = crash_status
        self.crashed = False

    async def record(self, identity: str, role: str, outcome: SendOutcome) -> None:
        await super().record(identity, role, outcome)
        if outcome.status == self.crash_status and not self.crashed:
            self.crashed = True
            raise SimulatedCrashError


@pytest.mark.asyncio
async def test_empty_diagnostics_replay_matches_uninterrupted_correction() -> None:
    base = generation_request()
    policy = GenerationRecoveryPolicy(3)
    empty_diagnostics_ledger = CrashAfterRecordLedger(GenerationOutcomeStatus.INVALID)
    uninterrupted_ledger = InMemoryGenerationLedger()

    def validator(
        receipt: RawGenerationReceipt, request: GenerationRequest
    ) -> ValidatedResponse[Payload]:
        if receipt.raw_candidate == "bad-complete-output":
            raise ResponseValidationError(())
        return validate_payload(receipt, request)

    class FirstAttemptProvider:
        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            return RawGenerationReceipt(
                text='{"value":"bad"}', raw_candidate="bad-complete-output"
            )

    with pytest.raises(SimulatedCrashError):
        await execute_generation(
            base,
            FirstAttemptProvider(),
            empty_diagnostics_ledger,
            policy,
            Adapter.OPENAI,
            validator=validator,
        )

    class CorrectionProvider:
        def __init__(self) -> None:
            self.requests: list[GenerationRequest] = []

        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            self.requests.append(request)
            return RawGenerationReceipt(text='{"value":13}')

    resumed_provider = CorrectionProvider()
    await execute_generation(
        base,
        resumed_provider,
        empty_diagnostics_ledger,
        policy,
        Adapter.OPENAI,
        validator=validator,
    )

    class UninterruptedProvider(CorrectionProvider):
        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            self.requests.append(request)
            if len(self.requests) == 1:
                return RawGenerationReceipt(
                    text='{"value":"bad"}', raw_candidate="bad-complete-output"
                )
            return RawGenerationReceipt(text='{"value":13}')

    uninterrupted_provider = UninterruptedProvider()
    await execute_generation(
        base,
        uninterrupted_provider,
        uninterrupted_ledger,
        policy,
        Adapter.OPENAI,
        validator=validator,
    )

    assert resumed_provider.requests[0].identity == uninterrupted_provider.requests[1].identity
    assert resumed_provider.requests[0].messages == uninterrupted_provider.requests[1].messages
    assert (
        resumed_provider.requests[0].initial_prefix_hash
        == uninterrupted_provider.requests[1].initial_prefix_hash
    )
    assert "bad-complete-output" in message_content(resumed_provider.requests[0].messages[-2])
    assert empty_diagnostics_ledger.send_count(execution_identity(base), base.role) == 2
