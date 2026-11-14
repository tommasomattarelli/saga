import json

import pytest

from app.ai.generation_contracts import (
    GenerationRequest,
    GenerationToolReceipt,
    RawGenerationReceipt,
    RawToolArguments,
)
from app.ai.generation_errors import Adapter
from app.ai.generation_execution import GenerationExecutionError, execute_generation
from app.ai.generation_execution_ledger import (
    GenerationRecoveryPolicy,
    InMemoryGenerationLedger,
)
from app.ai.response_validation import (
    DiagnosticCode,
    Normalization,
    ResponseValidationError,
    ValidatedResponse,
    ValidationDiagnostic,
)
from tests.unit.ai.generation_execution_test_support import (
    FakeProvider,
    Payload,
    execution_identity,
    generation_request,
    message_content,
    validate_payload,
)


@pytest.mark.asyncio
async def test_contextual_validation_failure_corrects_before_acceptance() -> None:
    base = generation_request()
    provider = FakeProvider(
        [RawGenerationReceipt(text='{"value":1}'), RawGenerationReceipt(text='{"value":2}')],
        [],
    )
    validations = 0

    def contextual_validator(
        receipt: RawGenerationReceipt, request: GenerationRequest
    ) -> ValidatedResponse[Payload]:
        nonlocal validations
        validations += 1
        result = validate_payload(receipt, request)
        if result.model.value == 1:
            raise ResponseValidationError(
                (ValidationDiagnostic(DiagnosticCode.BELOW_MINIMUM, ("value",)),)
            )
        return result

    result = await execute_generation(
        base,
        provider,
        InMemoryGenerationLedger(),
        GenerationRecoveryPolicy(3),
        Adapter.OPENAI,
        validator=contextual_validator,
    )
    assert result.value.value == 2
    assert validations == 2
    assert len(provider.requests) == 2


@pytest.mark.asyncio
async def test_tool_only_receipt_is_validated_as_a_whole_without_filler() -> None:

    base = generation_request()
    receipt = RawGenerationReceipt(
        text=None,
        tool_calls=(
            GenerationToolReceipt(
                call_id="call-1",
                name="move",
                arguments=RawToolArguments.structured({"direction": "north"}),
            ),
        ),
    )
    provider = FakeProvider([receipt], [])
    observed: list[RawGenerationReceipt] = []

    def tool_validator(
        actual: RawGenerationReceipt, derived: GenerationRequest
    ) -> ValidatedResponse[Payload]:
        observed.append(actual)
        assert derived.initial_prefix_hash == base.initial_prefix_hash
        assert actual.text is None and actual.tool_calls
        return ValidatedResponse(Payload(value=4), Normalization.NONE)

    result = await execute_generation(
        base,
        provider,
        InMemoryGenerationLedger(),
        GenerationRecoveryPolicy(1),
        Adapter.OPENAI,
        validator=tool_validator,
    )
    assert result.value.value == 4
    assert observed == [receipt]


@pytest.mark.asyncio
async def test_correction_uses_complete_raw_candidate_not_text() -> None:
    base = generation_request()
    raw = '{"value":"bad"} UNKNOWN_NATIVE_FIELD sig=opaque'
    provider = FakeProvider(
        [
            RawGenerationReceipt(text='{"value":"bad"}', raw_candidate=raw),
            RawGenerationReceipt(text='{"value":8}'),
        ],
        [],
    )
    await execute_generation(
        base,
        provider,
        InMemoryGenerationLedger(),
        GenerationRecoveryPolicy(2),
        Adapter.OPENAI,
        validator=validate_payload,
    )
    quoted_output = message_content(provider.requests[1].messages[-2]).split(
        "Untrusted model output JSON string: ", 1
    )[1]
    assert json.loads(quoted_output) == raw


@pytest.mark.asyncio
async def test_invalid_native_receipt_without_raw_candidate_stops_without_retry() -> None:

    base = generation_request()
    receipt = RawGenerationReceipt(
        text='{"value":"invalid"}',
        tool_calls=(
            GenerationToolReceipt(
                call_id="call-1",
                name="unknown",
                arguments=RawToolArguments.raw_text("{unparsed"),
            ),
        ),
    )
    provider = FakeProvider([receipt, RawGenerationReceipt(text='{"value":1}')], [])
    ledger = InMemoryGenerationLedger()
    with pytest.raises(GenerationExecutionError, match="no complete correction candidate"):
        await execute_generation(
            base,
            provider,
            ledger,
            GenerationRecoveryPolicy(3),
            Adapter.OPENAI,
            validator=validate_payload,
        )
    assert len(provider.requests) == 1
    outcome = (await ledger.history(execution_identity(base), base.role))[0].outcome
    assert outcome is not None
    assert outcome.receipt is receipt
    assert outcome.status == "invalid"
