from __future__ import annotations

import pytest

from app.ai.generation_contracts import (
    GenerationToolReceipt,
    RawGenerationReceipt,
    RawToolArguments,
)
from app.ai.generation_errors import Adapter
from app.ai.generation_execution_ledger import (
    GenerationExecutionError,
    GenerationExecutionIdentity,
    GenerationOutcomeStatus,
    GenerationRecoveryPolicy,
    InMemoryGenerationLedger,
)
from app.core.dm.dm_generation import DMNarrative, execute_dm_generation
from tests.unit.core.dm_generation_test_support import SequenceProvider
from tests.unit.core.test_dm_generation import _request


def _received_tool_call(
    name: str | None,
    arguments: RawToolArguments,
) -> GenerationToolReceipt:
    return GenerationToolReceipt(call_id="call-invalid", name=name, arguments=arguments)


@pytest.mark.asyncio
async def test_dm_executor_corrects_invalid_response_and_stops_after_valid() -> None:
    request = _request()
    provider = SequenceProvider(
        [
            RawGenerationReceipt(text='{"text":3}'),
            RawGenerationReceipt(text='{"text":"The door opens."}'),
        ]
    )
    ledger = InMemoryGenerationLedger()
    policy = GenerationRecoveryPolicy(max_sends_per_result=2)

    result = await execute_dm_generation(request, provider, ledger, policy, Adapter.OPENAI)

    identity = GenerationExecutionIdentity.create(request.identity, policy)
    assert result.value == DMNarrative(text="The door opens.")
    assert [send.status for send in result.sends] == [
        GenerationOutcomeStatus.INVALID,
        GenerationOutcomeStatus.VALID,
    ]
    assert len(provider.requests) == 2
    assert provider.requests[0].messages == request.messages
    assert provider.requests[1].messages != request.messages
    assert "Untrusted model output JSON string:" in repr(provider.requests[1].messages)
    assert ledger.send_count(identity.digest, "dm") == 2


@pytest.mark.asyncio
async def test_dm_executor_enforces_send_cap_without_an_extra_generation() -> None:
    request = _request()
    provider = SequenceProvider(
        [
            RawGenerationReceipt(text='{"text":3}'),
            RawGenerationReceipt(text='{"text":false}'),
        ]
    )
    ledger = InMemoryGenerationLedger()
    policy = GenerationRecoveryPolicy(max_sends_per_result=2)

    with pytest.raises(GenerationExecutionError, match="budget exhausted"):
        await execute_dm_generation(request, provider, ledger, policy, Adapter.OPENAI)

    identity = GenerationExecutionIdentity.create(request.identity, policy)
    assert len(provider.requests) == 2
    assert ledger.send_count(identity.digest, "dm") == 2


@pytest.mark.parametrize(
    ("allowed_tools", "call"),
    [
        (
            {"request_dice"},
            _received_tool_call("missing_tool", RawToolArguments.structured({"value": "x"})),
        ),
        (
            {"request_dice"},
            _received_tool_call("set_scene_mood", RawToolArguments.structured({"mood": "tense"})),
        ),
        (
            {"request_dice"},
            _received_tool_call("request_dice", RawToolArguments.raw_text("{broken")),
        ),
        (
            {"request_dice"},
            _received_tool_call("request_dice", RawToolArguments.raw_text("[]")),
        ),
        (
            {"request_dice"},
            _received_tool_call(
                "request_dice",
                RawToolArguments.structured(
                    {"check": "Stealth", "stat": "DEX", "difficulty": "impossible"}
                ),
            ),
        ),
    ],
)
@pytest.mark.asyncio
async def test_invalid_tool_response_is_recorded_then_corrected(
    allowed_tools: set[str], call: GenerationToolReceipt
) -> None:
    invalid = RawGenerationReceipt(
        text="",
        tool_calls=(call,),
        raw_candidate='{"candidate":"original invalid tool response"}',
    )
    request = _request(allowed_tools=allowed_tools)
    provider = SequenceProvider(
        [invalid, RawGenerationReceipt(text='{"text":"Corrected response."}')]
    )
    ledger = InMemoryGenerationLedger()
    policy = GenerationRecoveryPolicy(max_sends_per_result=2)

    result = await execute_dm_generation(request, provider, ledger, policy, Adapter.OPENAI)

    assert result.value.text == "Corrected response."
    assert [send.status for send in result.sends] == [
        GenerationOutcomeStatus.INVALID,
        GenerationOutcomeStatus.VALID,
    ]
    assert len(provider.requests) == 2
    assert result.sends[0].receipt is invalid
    assert result.sends[0].receipt.tool_calls[0].arguments == call.arguments
    assert "original invalid tool response" in repr(provider.requests[1].messages)


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        (
            "update_npc",
            RawToolArguments.structured(
                {
                    "name": "Mara",
                    "updates": [
                        {"key": "condition", "value": "wounded"},
                        {"key": "condition", "value": "well"},
                    ],
                }
            ),
        ),
        (
            "change_npc_psychology",
            RawToolArguments.structured(
                {
                    "npc": "Mara",
                    "changes": [{"key": "trust", "value": 1, "unknown": True}],
                }
            ),
        ),
    ],
)
@pytest.mark.asyncio
async def test_invalid_wire_tool_arguments_are_corrected(
    name: str, arguments: RawToolArguments
) -> None:
    call = _received_tool_call(name, arguments)
    request = _request(allowed_tools={name})
    provider = SequenceProvider(
        [
            RawGenerationReceipt(
                text=None,
                tool_calls=(call,),
                raw_candidate='{"candidate":"invalid wire arguments"}',
            ),
            RawGenerationReceipt(text='{"text":"Corrected response."}'),
        ]
    )

    result = await execute_dm_generation(
        request,
        provider,
        InMemoryGenerationLedger(),
        GenerationRecoveryPolicy(max_sends_per_result=2),
        Adapter.OPENAI,
    )

    assert result.value.text == "Corrected response."
    assert [send.status for send in result.sends] == [
        GenerationOutcomeStatus.INVALID,
        GenerationOutcomeStatus.VALID,
    ]
    assert len(provider.requests) == 2
