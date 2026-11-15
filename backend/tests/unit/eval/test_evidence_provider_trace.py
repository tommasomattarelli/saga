from unittest.mock import AsyncMock, Mock

import pytest
from eval.support.provider_trace import ProviderTrace

from app.ai.generation_contracts import GenerationRequest, OutputLimit, RawGenerationReceipt
from app.ai.providers.usage import capture_usage, current_correlation
from app.ai.response_contracts import ResponseContract
from app.core.dm.dm_generation import DMNarrative


def _generation_request() -> GenerationRequest:
    return GenerationRequest.create(
        "DM prompt",
        [{"role": "user", "content": "Player action"}],
        contract=ResponseContract("dm-narrative", "v1", DMNarrative),
        provider="openrouter",
        model="m:free",
        destination_fingerprint="test:destination",
        role="dm",
        logical_result_id="result-1",
        output_limit=OutputLimit(500),
        session_affinity="session-1",
    )


@pytest.mark.asyncio
async def test_provider_trace_role_override_keeps_default_actor() -> None:
    observed: list[str | None] = []

    async def generate(**_request: object) -> str:
        observed.append(current_correlation().role)
        return "{}"

    provider = Mock()
    provider.generate = AsyncMock(side_effect=generate)
    await ProviderTrace(provider).generate("system", [], "model")
    await ProviderTrace(provider, role="memory_unified").generate("system", [], "model")
    assert observed == ["actor", "memory_unified"]


@pytest.mark.asyncio
async def test_provider_trace_send_retains_typed_request_receipt_and_usage() -> None:
    roles: list[str | None] = []
    receipt = RawGenerationReceipt(text='{"text":"The square is quiet."}')

    async def send(request: GenerationRequest) -> RawGenerationReceipt:
        roles.append(current_correlation().role)
        capture_usage({"id": "response-1", "usage": {"prompt_tokens": 9}}, model=request.model)
        return receipt

    provider = Mock()
    provider.send = AsyncMock(side_effect=send)
    trace = ProviderTrace(provider)
    request = _generation_request()

    result = await trace.send(request)

    assert result is receipt
    assert provider.send.await_args.args == (request,)
    assert trace.request["identity"] == request.identity.digest
    assert trace.request["session_affinity"] == "session-1"
    assert trace.response["text"] == receipt.text
    assert trace.usage[0].response_id == "response-1"
    assert roles == ["dm"]
