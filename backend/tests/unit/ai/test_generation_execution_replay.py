import pytest

from app.ai.generation_contracts import FormatMode, GenerationRequest, RawGenerationReceipt
from app.ai.generation_errors import Adapter, SchemaModeUnsupportedBeforeIO
from app.ai.generation_execution import GenerationExecutionError, execute_generation
from app.ai.generation_execution_ledger import (
    GenerationAttempt,
    GenerationOutcomeStatus,
    GenerationRecoveryPolicy,
    GenerationSendKind,
    InMemoryGenerationLedger,
)
from app.ai.providers.local import OpenAICompatibleResponseError
from tests.unit.ai.generation_execution_test_support import (
    assert_reserved_attempt,
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

    async def record(self, identity: str, role: str, outcome) -> None:
        await super().record(identity, role, outcome)
        if outcome.status == self.crash_status and not self.crashed:
            self.crashed = True
            raise SimulatedCrashError


@pytest.mark.asyncio
async def test_invalid_recorded_before_crash_resumes_with_correction() -> None:
    base = generation_request()
    ledger = CrashAfterRecordLedger("invalid")
    policy = GenerationRecoveryPolicy(3)

    class FirstProvider:
        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            await assert_reserved_attempt(ledger, base, request, GenerationSendKind.INITIAL)
            return RawGenerationReceipt(
                text='{"value":"failed"}', raw_candidate="complete-failed-output"
            )

    with pytest.raises(SimulatedCrashError):
        await execute_generation(
            base,
            FirstProvider(),
            ledger,
            policy,
            Adapter.OPENAI,
            validator=validate_payload,
        )

    sends = await ledger.history(execution_identity(base), base.role)
    assert sends[0].reservation.attempt.send_kind is GenerationSendKind.INITIAL
    assert sends[0].outcome is not None

    class ResumedProvider:
        def __init__(self) -> None:
            self.requests: list[GenerationRequest] = []

        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            self.requests.append(request)
            await assert_reserved_attempt(ledger, base, request, GenerationSendKind.CORRECTION)
            return RawGenerationReceipt(text='{"value":4}')

    resumed = ResumedProvider()
    result = await execute_generation(
        base,
        resumed,
        ledger,
        policy,
        Adapter.OPENAI,
        validator=validate_payload,
    )
    assert result.value.value == 4
    assert len(resumed.requests) == 1
    assert resumed.requests[0].identity.digest != base.identity.digest
    assert "complete-failed-output" in message_content(resumed.requests[0].messages[-2])
    history = await ledger.history(execution_identity(base), base.role)
    assert history[1].reservation.attempt.send_kind is GenerationSendKind.CORRECTION


@pytest.mark.asyncio
async def test_unsupported_corrective_send_crash_resumes_authorized_fallback_with_history() -> (
    None
):
    base = generation_request(allow_json=True)
    ledger = CrashAfterRecordLedger("schema_mode_unsupported")
    policy = GenerationRecoveryPolicy(3)

    class FailingProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            self.calls += 1
            await assert_reserved_attempt(
                ledger,
                base,
                request,
                GenerationSendKind.INITIAL if self.calls == 1 else GenerationSendKind.CORRECTION,
            )
            if self.calls == 1:
                return RawGenerationReceipt(
                    text='{"value":"failed"}', raw_candidate="first-complete-candidate"
                )
            raise SchemaModeUnsupportedBeforeIO

    with pytest.raises(SimulatedCrashError):
        await execute_generation(
            base,
            FailingProvider(),
            ledger,
            policy,
            Adapter.OPENAI,
            validator=validate_payload,
        )
    prior = await ledger.history(execution_identity(base), base.role)
    assert [send.reservation.attempt.send_kind for send in prior] == [
        GenerationSendKind.INITIAL,
        GenerationSendKind.CORRECTION,
    ]

    class FallbackProvider:
        def __init__(self) -> None:
            self.requests: list[GenerationRequest] = []

        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            self.requests.append(request)
            await assert_reserved_attempt(ledger, base, request, GenerationSendKind.FALLBACK)
            return RawGenerationReceipt(text='{"value":5}')

    provider = FallbackProvider()
    result = await execute_generation(
        base,
        provider,
        ledger,
        policy,
        Adapter.OPENAI,
        validator=validate_payload,
    )
    assert result.value.value == 5
    assert provider.requests[0].format_mode is FormatMode.JSON_MODE
    assert provider.requests[0].initial_prefix_hash != base.initial_prefix_hash
    assert "first-complete-candidate" in message_content(provider.requests[0].messages[-2])
    history = await ledger.history(execution_identity(base), base.role)
    assert history[2].reservation.attempt.send_kind is GenerationSendKind.FALLBACK


@pytest.mark.asyncio
async def test_unresolved_reservation_is_uncertain_and_never_resends_base() -> None:
    base = generation_request()
    ledger = InMemoryGenerationLedger()
    attempt = GenerationAttempt(
        base.identity.digest,
        base.format_mode,
        GenerationSendKind.INITIAL,
    )
    await ledger.reserve(
        execution_identity(base),
        base.role,
        3,
        attempt,
    )

    class NoSendProvider:
        calls = 0

        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            self.calls += 1
            return RawGenerationReceipt(text='{"value":1}')

    provider = NoSendProvider()
    with pytest.raises(GenerationExecutionError, match="uncertain"):
        await execute_generation(
            base,
            provider,
            ledger,
            GenerationRecoveryPolicy(3),
            Adapter.OPENAI,
            validator=validate_payload,
        )
    assert provider.calls == 0
    history = await ledger.history(execution_identity(base), base.role)
    assert len(history) == 1 and history[0].outcome is None


@pytest.mark.asyncio
async def test_recorded_transport_retry_resumes_with_retry_provenance() -> None:
    base = generation_request()
    ledger = CrashAfterRecordLedger(GenerationOutcomeStatus.RATE_LIMIT)
    policy = GenerationRecoveryPolicy(3)

    class RateLimitedProvider:
        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            await assert_reserved_attempt(ledger, base, request, GenerationSendKind.INITIAL)
            raise OpenAICompatibleResponseError(
                "openrouter",
                code=429,
                status=None,
                error_type=None,
            )

    with pytest.raises(SimulatedCrashError):
        await execute_generation(
            base,
            RateLimitedProvider(),
            ledger,
            policy,
            Adapter.OPENROUTER,
            validator=validate_payload,
        )

    class RetryProvider:
        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            await assert_reserved_attempt(
                ledger, base, request, GenerationSendKind.TRANSPORT_RETRY
            )
            return RawGenerationReceipt(text='{"value":10}')

    result = await execute_generation(
        base,
        RetryProvider(),
        ledger,
        policy,
        Adapter.OPENROUTER,
        validator=validate_payload,
    )
    assert result.value.value == 10
    history = await ledger.history(execution_identity(base), base.role)
    assert [send.reservation.attempt.send_kind for send in history] == [
        GenerationSendKind.INITIAL,
        GenerationSendKind.TRANSPORT_RETRY,
    ]


@pytest.mark.asyncio
async def test_recorded_valid_candidate_is_revalidated_and_reused_without_io() -> None:
    base = generation_request()
    ledger = InMemoryGenerationLedger()
    policy = GenerationRecoveryPolicy(3)

    class Provider:
        calls = 0

        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            self.calls += 1
            return RawGenerationReceipt(text='{"value":12}')

    provider = Provider()
    first = await execute_generation(
        base, provider, ledger, policy, Adapter.OPENAI, validator=validate_payload
    )
    reused = await execute_generation(
        base, provider, ledger, policy, Adapter.OPENAI, validator=validate_payload
    )
    assert first.value == reused.value
    assert provider.calls == 1
