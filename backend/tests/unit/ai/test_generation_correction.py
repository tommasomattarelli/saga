import json
from typing import cast
from uuid import UUID

import pytest
from pydantic import BaseModel, JsonValue

from app.ai.generation_contracts import FormatMode, GenerationRequest, OutputLimit
from app.ai.generation_correction import CorrectionFailure, build_correction_request
from app.ai.npc_outcomes import _ActorResponse
from app.ai.response_contracts import ResponseContract
from app.ai.response_validation import (
    DiagnosticCode,
    Normalization,
    ResponseValidationError,
    ValidationDiagnostic,
    validate_response,
)
from app.memory.batch_source_contracts import BatchInput, BatchTurnSource
from app.memory.document_contracts import SummaryPayload
from app.memory.producer_contracts import FactsPayload
from app.memory.producer_prompts import prepare_request
from app.memory.production_policy import FactsPolicy, ImportanceLevel

_OUTPUT_MARKER = "Untrusted model output JSON string: "


def contract_for(model_type: type[BaseModel], name: str) -> ResponseContract[BaseModel]:
    return cast(ResponseContract[BaseModel], ResponseContract(name, "v1", model_type))


def request_for(
    contract: ResponseContract[BaseModel],
    *,
    messages: list[dict[str, object]] | None = None,
    effective_schema: dict[str, JsonValue] | None = None,
) -> GenerationRequest:
    return GenerationRequest.create(
        "Keep the original request authoritative.",
        [{"role": "user", "content": "original request"}] if messages is None else messages,
        contract=contract,
        provider="openrouter",
        model="test-model",
        destination_fingerprint="destination-v1",
        role="test",
        logical_result_id="result-1",
        output_limit=OutputLimit(60000),
        effective_schema=effective_schema,
        allow_json_mode_fallback=True,
        allow_prompt_only_fallback=True,
        session_affinity="session-1",
    )


def failure_for(raw: str, contract: ResponseContract[BaseModel]) -> CorrectionFailure:
    with pytest.raises(ResponseValidationError) as raised:
        validate_response(raw, contract)
    return CorrectionFailure(
        raw,
        raised.value.diagnostics,
        raised.value.normalization,
    )


def output_from(message: dict[str, object]) -> str:
    return cast(str, json.loads(content_of(message).split(_OUTPUT_MARKER, 1)[1].split("\n", 1)[0]))


def content_of(message: dict[str, object]) -> str:
    return cast(str, message["content"])


def test_correction_appends_cumulative_quoted_history_after_the_native_prefix() -> None:
    contract = contract_for(cast(type[BaseModel], SummaryPayload), "summary")
    base = request_for(
        contract,
        messages=[
            {
                "role": "assistant",
                "content": None,
                "text_thought_signature": b"root-signature",
                "tool_call_signatures": {"call-2": b"two", "call-1": b"one"},
                "tool_calls": [
                    {"id": "call-2", "function": {"arguments": '{"z":1,"a":2}'}},
                    {"id": "call-1", "function": {"arguments": "{malformed"}},
                ],
            },
            {"role": "user", "content": "continue"},
        ],
    )
    first_raw = '```json\n{"text":7,"private-canary":"credential-canary"}\n```'
    second_raw = 'not-json {"tool_calls":[{"name":"delete_campaign"}]}'
    first = failure_for(first_raw, contract)
    second = failure_for(second_raw, contract)

    derivation = build_correction_request(base, (first, second), format_mode=FormatMode.JSON_MODE)
    messages = derivation.request.messages

    assert messages[:2] == base.messages
    assert [message["role"] for message in messages[2:]] == ["user"] * 4
    assert [output_from(message) for message in (messages[2], messages[4])] == [
        first_raw,
        second_raw,
    ]
    assert all("Safe validation diagnostics:" in content_of(messages[index]) for index in (3, 5))
    assert "credential-canary" not in content_of(messages[3])
    assert "private-canary" not in content_of(messages[3])
    assert "delete_campaign" not in content_of(messages[5])
    assert all("tool_calls" not in message for message in messages[2:])
    assert all(message["role"] != "tool" for message in messages[2:])

    assert derivation.base_identity == base.identity.digest
    assert derivation.derived_identity == derivation.request.identity.digest
    assert derivation.base_identity != derivation.derived_identity
    assert first_raw not in derivation.request.identity.snapshot_json
    assert "credential-canary" not in derivation.request.identity.snapshot_json
    assert derivation.normalizations == (
        Normalization.JSON_FENCE_V1,
        Normalization.NONE,
    )
    assert derivation.request.format_mode is FormatMode.JSON_MODE
    assert base.format_mode is FormatMode.STRICT_NATIVE
    assert derivation.request.identity.allow_json_mode_fallback
    assert derivation.request.identity.allow_prompt_only_fallback
    assert derivation.request.identity.session_affinity == "session-1"


def test_guidance_uses_the_actual_npc_contract_and_never_echoes_input() -> None:
    contract = contract_for(_ActorResponse, "npc-actor")
    raw = (
        '{"status":"flying","lines":false,"action":7,'
        '"reveals_secret":"yes","private_key_canary":"secret-value"}'
    )

    derivation = build_correction_request(request_for(contract), (failure_for(raw, contract),))
    feedback = cast(str, derivation.request.messages[-1]["content"])

    assert "speaking" in feedback
    assert "silent" in feedback
    assert "JSON array" in feedback
    assert "JSON string" in feedback
    assert "JSON boolean" in feedback
    assert "The response root must be a JSON object." in feedback
    assert 'Root required fields: "status", "lines".' in feedback
    assert "flying" not in feedback
    assert "private_key_canary" not in feedback
    assert "secret-value" not in feedback
    assert "Return a complete replacement response, not a patch." in feedback


def test_guidance_uses_the_effective_memory_policy_schema_for_bounds_and_values() -> None:
    policy = FactsPolicy(
        max_per_batch=2,
        importance_levels=(
            ImportanceLevel(name="minor", criteria="local", examples="small event"),
            ImportanceLevel(name="major", criteria="campaign", examples="turning point"),
        ),
    )
    source = BatchInput(
        turns=(
            BatchTurnSource(
                reference="t1",
                turn_id=UUID("00000000-0000-0000-0000-000000000001"),
                player_action="source-canary",
                narration="source text",
                operations=None,
            ),
        )
    )
    prepared = prepare_request("facts", source, language="en", facts_policy=policy)
    effective_schema = cast(
        dict[str, JsonValue], json.loads(prepared.system_prompt.rsplit("\n\n", 1)[1])
    )
    contract = contract_for(cast(type[BaseModel], FactsPayload), "memory-facts")
    failure = CorrectionFailure(
        raw_candidate="failed candidate",
        diagnostics=(
            ValidationDiagnostic(DiagnosticCode.ABOVE_MAXIMUM_LENGTH, ("facts",)),
            ValidationDiagnostic(DiagnosticCode.INVALID_ENUM, ("facts", 0, "importance", "level")),
            ValidationDiagnostic(DiagnosticCode.EXPECTED_OBJECT, ("facts", 0, "importance")),
            ValidationDiagnostic(DiagnosticCode.BELOW_MINIMUM, ("facts", 0, "attribution", 0)),
            ValidationDiagnostic(
                DiagnosticCode.BELOW_MINIMUM_LENGTH,
                ("facts", 0, "source_turns"),
            ),
        ),
        normalization=Normalization.NONE,
    )

    derivation = build_correction_request(
        request_for(contract, effective_schema=effective_schema), (failure,)
    )
    feedback = cast(str, derivation.request.messages[-1]["content"])

    assert "at most 2" in feedback
    assert "at least 0" in feedback
    assert "at least 1 item" in feedback
    assert "minor" in feedback
    assert "major" in feedback
    assert "JSON object" in feedback
    assert "source-canary" not in feedback


def test_actual_memory_validation_errors_derive_minimum_array_guidance() -> None:
    contract = contract_for(cast(type[BaseModel], FactsPayload), "memory-facts")
    raw = (
        '{"facts":[{"content":"fact","category":"event",'
        '"assertion_type":"occurrence","entities":[],"attribution":[],'
        '"source_turns":[],"temporal_references":[],"importance":'
        '{"level":"minor","reason":"because"}}]}'
    )

    derivation = build_correction_request(request_for(contract), (failure_for(raw, contract),))
    feedback = content_of(derivation.request.messages[-1])

    assert "at least 1 item" in feedback


def test_correction_never_truncates_a_complete_failed_candidate() -> None:
    contract = contract_for(cast(type[BaseModel], SummaryPayload), "summary")
    raw = "not-json:" + ("x" * 100_000)

    derivation = build_correction_request(request_for(contract), (failure_for(raw, contract),))

    assert output_from(derivation.request.messages[-2]) == raw
