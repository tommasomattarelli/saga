from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from pydantic import BaseModel, ConfigDict

from app.ai.generation_contracts import (
    GenerationRequest,
    OutputLimit,
    RawGenerationReceipt,
)
from app.ai.generation_execution_ledger import (
    GenerationLedger,
    GenerationSendKind,
)
from app.ai.response_contracts import ResponseContract
from app.ai.response_validation import (
    DiagnosticCode,
    ResponseValidationError,
    ValidatedResponse,
    ValidationDiagnostic,
    validate_response,
)


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: int


def generation_request(*, allow_json: bool = False) -> GenerationRequest:
    return GenerationRequest.create(
        "instructions",
        [{"role": "user", "content": "prompt"}],
        contract=ResponseContract("payload", "v1", Payload),
        provider="openai",
        model="model",
        destination_fingerprint="destination",
        role="test",
        logical_result_id="result",
        output_limit=OutputLimit(100),
        allow_json_mode_fallback=allow_json,
    )


def execution_identity(base: GenerationRequest, limit: int = 3) -> str:
    from app.ai.generation_execution_ledger import (
        GenerationExecutionIdentity,
        GenerationRecoveryPolicy,
    )

    return GenerationExecutionIdentity.create(
        base.identity, GenerationRecoveryPolicy(limit)
    ).digest


def validate_payload(
    receipt: RawGenerationReceipt, request: GenerationRequest
) -> ValidatedResponse[Payload]:
    if receipt.text is None:
        raise ResponseValidationError((ValidationDiagnostic(DiagnosticCode.INVALID_JSON, ()),))
    return validate_response(receipt.text, cast(ResponseContract[Payload], request.contract))


def message_content(message: dict[str, object]) -> str:
    content = message.get("content")
    assert isinstance(content, str)
    return content


async def assert_reserved_attempt(
    ledger: GenerationLedger,
    base: GenerationRequest,
    request: GenerationRequest,
    kind: GenerationSendKind,
    max_sends: int = 3,
) -> None:
    sends = await ledger.history(execution_identity(base, max_sends), base.role)
    assert sends
    attempt = sends[-1].reservation.attempt
    assert attempt.send_kind is kind
    assert attempt.request_identity == request.identity.digest
    assert attempt.format_mode is request.format_mode


@dataclass
class FakeProvider:
    receipts: list[RawGenerationReceipt]
    requests: list[GenerationRequest]

    async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
        self.requests.append(request)
        return self.receipts.pop(0)
