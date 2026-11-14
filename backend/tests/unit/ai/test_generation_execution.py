import httpx
import pytest
from openai import APIStatusError, AsyncOpenAI

from app.ai.generation_contracts import (
    FormatMode,
    GenerationRequest,
    RawGenerationReceipt,
)
from app.ai.generation_errors import (
    Adapter,
    SchemaModeUnsupportedBeforeIO,
    classify_failure,
)
from app.ai.generation_execution import (
    GenerationExecutionError,
    GenerationExecutionIdentity,
    GenerationRecoveryPolicy,
    _exception_signals,
    execute_generation,
)
from app.ai.generation_execution_ledger import (
    GenerationAttempt,
    GenerationSendKind,
    InMemoryGenerationLedger,
)
from app.ai.providers.local import OpenAICompatibleResponseError
from tests.unit.ai.generation_execution_test_support import (
    FakeProvider,
    Payload,
    assert_reserved_attempt,
    execution_identity,
    generation_request,
    message_content,
    validate_payload,
)


@pytest.mark.asyncio
async def test_invalid_then_cumulative_correction_with_shared_send_cap() -> None:
    base = generation_request()
    provider = FakeProvider(
        [RawGenerationReceipt(text='{"value":"bad"}'), RawGenerationReceipt(text='{"value":2}')],
        [],
    )
    ledger = InMemoryGenerationLedger()
    result = await execute_generation(
        base,
        provider,
        ledger,
        GenerationRecoveryPolicy(3),
        Adapter.OPENAI,
        validator=validate_payload,
    )
    assert result.value == Payload(value=2)
    assert ledger.send_count(execution_identity(base), base.role) == 2
    assert "bad" in message_content(provider.requests[1].messages[-2])


@pytest.mark.asyncio
async def test_correction_request_retains_every_failed_candidate() -> None:
    base = generation_request()
    provider = FakeProvider(
        [
            RawGenerationReceipt(text='{"value":"first"}'),
            RawGenerationReceipt(text='{"value":"second"}'),
            RawGenerationReceipt(text='{"value":3}'),
        ],
        [],
    )
    await execute_generation(
        base,
        provider,
        InMemoryGenerationLedger(),
        GenerationRecoveryPolicy(3),
        Adapter.OPENAI,
        validator=validate_payload,
    )
    correction = provider.requests[2].messages
    assert "first" in message_content(correction[-4])
    assert "second" in message_content(correction[-2])


@pytest.mark.asyncio
async def test_preused_send_is_not_refunded_or_reset() -> None:
    base = generation_request()
    ledger = InMemoryGenerationLedger()
    await ledger.reserve(
        execution_identity(base, 1),
        base.role,
        1,
        GenerationAttempt(
            base.identity.digest,
            base.format_mode,
            GenerationSendKind.INITIAL,
        ),
    )
    provider = FakeProvider([RawGenerationReceipt(text='{"value":1}')], [])
    with pytest.raises(GenerationExecutionError):
        await execute_generation(
            base,
            provider,
            ledger,
            GenerationRecoveryPolicy(1),
            Adapter.OPENAI,
            validator=validate_payload,
        )
    assert ledger.send_count(execution_identity(base, 1), base.role) == 1
    assert not provider.requests


@pytest.mark.asyncio
async def test_unsupported_native_then_authorized_fallback_shares_budget() -> None:
    base = generation_request(allow_json=True)
    ledger = InMemoryGenerationLedger()

    class FallbackProvider:
        def __init__(self) -> None:
            self.requests: list[GenerationRequest] = []

        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            self.requests.append(request)
            await assert_reserved_attempt(
                ledger,
                base,
                request,
                GenerationSendKind.INITIAL
                if len(self.requests) == 1
                else GenerationSendKind.FALLBACK,
                max_sends=2,
            )
            if len(self.requests) == 1:
                raise SchemaModeUnsupportedBeforeIO
            return RawGenerationReceipt(text='{"value":7}')

    provider = FallbackProvider()
    result = await execute_generation(
        base,
        provider,
        ledger,
        GenerationRecoveryPolicy(2),
        Adapter.OPENAI,
        validator=validate_payload,
    )
    assert result.value.value == 7
    assert [item.format_mode for item in provider.requests] == [
        FormatMode.STRICT_NATIVE,
        FormatMode.JSON_MODE,
    ]
    assert ledger.send_count(execution_identity(base, 2), base.role) == 2


@pytest.mark.asyncio
async def test_inband_openrouter_429_retries_from_structured_code_only() -> None:
    base = generation_request()
    ledger = InMemoryGenerationLedger()

    class RetryProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            self.calls += 1
            await assert_reserved_attempt(
                ledger,
                base,
                request,
                GenerationSendKind.INITIAL
                if self.calls == 1
                else GenerationSendKind.TRANSPORT_RETRY,
                max_sends=2,
            )
            if self.calls == 1:
                raise OpenAICompatibleResponseError(
                    "openrouter",
                    code=429,
                    status=None,
                    error_type=None,
                )
            return RawGenerationReceipt(text='{"value":9}')

    result = await execute_generation(
        base,
        RetryProvider(),
        ledger,
        GenerationRecoveryPolicy(2),
        Adapter.OPENROUTER,
        validator=validate_payload,
    )
    assert result.value.value == 9


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "error_type", "expected"),
    [
        ("rate_limit_exceeded", "rate_limit_error", "rate_limit"),
        ("insufficient_quota", "insufficient_quota", "stop"),
    ],
)
async def test_openai_sdk_status_body_shape_preserves_429_taxonomy(
    code: str, error_type: str, expected: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "error": {
                    "message": "offline provider error",
                    "code": code,
                    "type": error_type,
                }
            },
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncOpenAI(api_key="offline", http_client=http_client, max_retries=0)
    try:
        with pytest.raises(APIStatusError) as captured:
            await client.chat.completions.create(
                model="offline",
                messages=[{"role": "user", "content": "test"}],
            )
    finally:
        await client.close()

    error = captured.value
    assert error.body == {
        "message": "offline provider error",
        "code": code,
        "type": error_type,
    }
    classification = classify_failure(_exception_signals(Adapter.OPENAI, error))
    assert classification.action.value == expected


def test_status_error_field_extraction_accepts_nested_error_payload() -> None:
    request = httpx.Request("POST", "https://example.invalid")
    response = httpx.Response(429, request=request)
    error = APIStatusError(
        "provider request failed",
        response=response,
        body={"error": {"code": "rate_limit_exceeded", "type": "rate_limit_error"}},
    )
    classification = classify_failure(_exception_signals(Adapter.OPENAI, error))
    assert classification.action.value == "rate_limit"


def test_execution_identity_changes_with_policy_without_mutating_base() -> None:
    base = generation_request()
    identity = GenerationExecutionIdentity.create(base.identity, GenerationRecoveryPolicy(3))
    changed = GenerationExecutionIdentity.create(base.identity, GenerationRecoveryPolicy(2))
    assert identity.digest != changed.digest
    assert base.identity.digest != identity.digest
