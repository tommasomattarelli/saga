import base64
import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from typing import cast

import pytest
from pydantic import BaseModel, ConfigDict, JsonValue

from app.ai.generation_contracts import (
    FormatMode,
    GenerationIdentity,
    GenerationRequest,
    GenerationToolReceipt,
    OutputLimit,
    RawGenerationReceipt,
    RawToolArguments,
)
from app.ai.providers.schemas import TEXT_SIGNATURE_KEY, TOOL_CALL_SIGNATURES_KEY
from app.ai.response_contracts import ResponseContract


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: str


class WirePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: str


class OtherWirePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: str
    extra: str


def make_identity(**changes: object) -> GenerationIdentity:
    values: dict[str, object] = {
        "role": "memory_summary",
        "logical_result_id": "result-1",
        "initial_prefix_hash": "prefix-hash",
        "wire_model": WirePayload,
        "wire_encoding_version": "wire-v1",
        "contextual_validator_version": "validator-v1",
        "provider": "openrouter",
        "model": "model-a",
        "destination_fingerprint": "destination-a",
        "output_limit": OutputLimit(configured_ceiling=60000),
        "format_mode": FormatMode.STRICT_NATIVE,
        "allow_json_mode_fallback": False,
        "allow_prompt_only_fallback": False,
        "session_affinity": "campaign-1",
    }
    values.update(changes)
    return GenerationIdentity.create(
        contract=ResponseContract("payload", "v1", Payload),
        role=cast(str, values["role"]),
        logical_result_id=cast(str, values["logical_result_id"]),
        initial_prefix_hash=cast(str, values["initial_prefix_hash"]),
        wire_model=cast(type[BaseModel], values["wire_model"]),
        wire_encoding_version=cast(str, values["wire_encoding_version"]),
        contextual_validator_version=cast(str, values["contextual_validator_version"]),
        provider=cast(str, values["provider"]),
        model=cast(str, values["model"]),
        destination_fingerprint=cast(str, values["destination_fingerprint"]),
        output_limit=cast(OutputLimit, values["output_limit"]),
        format_mode=cast(FormatMode, values["format_mode"]),
        allow_json_mode_fallback=cast(bool, values["allow_json_mode_fallback"]),
        allow_prompt_only_fallback=cast(bool, values["allow_prompt_only_fallback"]),
        session_affinity=cast(str | None, values["session_affinity"]),
    )


def make_request(**changes: object) -> GenerationRequest:
    values: dict[str, object] = {
        "system_prompt": "system",
        "messages": [{"role": "user", "content": "start"}],
        "contract": ResponseContract("payload", "v1", Payload),
        "provider": "openrouter",
        "model": "model-a",
        "destination_fingerprint": "destination-a",
        "role": "memory_summary",
        "logical_result_id": "result-1",
        "output_limit": OutputLimit(configured_ceiling=60000),
    }
    values.update(changes)
    return GenerationRequest.create(
        cast(str, values["system_prompt"]),
        cast(list[dict[str, object]], values["messages"]),
        contract=cast(ResponseContract[BaseModel], values["contract"]),
        provider=cast(str, values["provider"]),
        model=cast(str, values["model"]),
        destination_fingerprint=cast(str, values["destination_fingerprint"]),
        role=cast(str, values["role"]),
        logical_result_id=cast(str, values["logical_result_id"]),
        output_limit=cast(OutputLimit, values["output_limit"]),
        tool_declarations=cast(list[dict[str, object]] | None, values.get("tool_declarations")),
        wire_model=cast(type[BaseModel] | None, values.get("wire_model")),
        wire_schema=cast(dict[str, JsonValue] | None, values.get("wire_schema")),
        effective_schema=cast(dict[str, JsonValue] | None, values.get("effective_schema")),
    )


def test_request_freezes_prefix_and_returns_isolated_decoded_copies() -> None:
    messages: list[dict[str, object]] = [
        {
            "role": "assistant",
            "content": None,
            "tool_call_signatures": {"call-1": b"opaque\x00sig"},
            "text_thought_signature": b"text-sig",
            "tool_calls": [{"function": {"arguments": "{bad json"}}],
        },
        {"role": "user", "content": ""},
    ]
    request = GenerationRequest.create(
        "system",
        messages,
        contract=ResponseContract("payload", "v1", Payload),
        provider="openrouter",
        model="model-a",
        destination_fingerprint="destination-a",
        role="memory_summary",
        logical_result_id="result-1",
        output_limit=OutputLimit(60000),
    )
    original = cast(dict[str, object], messages[0])
    original["content"] = "mutated"
    cast(dict[str, bytes], original["tool_call_signatures"])["call-1"] = b"changed"

    first = request.messages
    assert first[0]["content"] is None
    assert first[1]["content"] == ""
    tool_calls = cast(list[dict[str, object]], first[0]["tool_calls"])
    function = cast(dict[str, object], tool_calls[0]["function"])
    assert function["arguments"] == "{bad json"
    assert cast(dict[str, bytes], first[0][TOOL_CALL_SIGNATURES_KEY])["call-1"] == b"opaque\x00sig"
    assert first[0][TEXT_SIGNATURE_KEY] == b"text-sig"
    cast(dict[str, bytes], first[0]["tool_call_signatures"])["call-1"] = b"caller mutation"
    assert (
        cast(dict[str, bytes], request.messages[0][TOOL_CALL_SIGNATURES_KEY])["call-1"]
        == b"opaque\x00sig"
    )
    snapshot = request.snapshot_json
    assert base64.b64encode(b"opaque\x00sig").decode() in snapshot


def test_identity_hashes_canonical_and_wire_schemas_and_effective_policy() -> None:
    base = make_identity()
    for changed in (
        {"provider": "openai"},
        {"model": "model-b"},
        {"destination_fingerprint": "destination-b"},
        {"contextual_validator_version": "validator-v2"},
        {"wire_model": OtherWirePayload},
        {"wire_encoding_version": "wire-v2"},
        {"format_mode": FormatMode.JSON_MODE},
        {"allow_json_mode_fallback": True},
        {"allow_prompt_only_fallback": True},
        {"session_affinity": "campaign-2"},
        {
            "output_limit": OutputLimit(
                configured_ceiling=60000, known_lower_limit=12000, limit_source="provider metadata"
            )
        },
    ):
        assert make_identity(**changed).digest != base.digest
    assert "credential" not in base.snapshot_json.lower()
    assert "api_key" not in base.snapshot_json.lower()
    assert "secret" not in base.snapshot_json.lower()
    assert "WirePayload" not in base.snapshot_json
    assert base.contract_schema_hash != ""
    assert base.wire_schema_hash != ""


def test_output_limit_uses_known_lower_limit_only_when_provided() -> None:
    assert OutputLimit(configured_ceiling=60000).effective == 60000
    assert (
        OutputLimit(
            configured_ceiling=60000,
            known_lower_limit=16000,
            limit_source="reliable profile metadata",
        ).effective
        == 16000
    )
    with pytest.raises(ValueError):
        OutputLimit(configured_ceiling=60000, known_lower_limit=16000)


def test_receipt_preserves_raw_tool_arguments_and_unvalidated_output() -> None:
    malformed = RawToolArguments.raw_text("{not json")
    structured = RawToolArguments.structured({"key": [1, None]})
    receipt = RawGenerationReceipt(
        text=None,
        tool_calls=(
            GenerationToolReceipt("call-1", "do_thing", malformed),
            GenerationToolReceipt("call-2", "do_other", structured),
        ),
        finish_reason="stop",
        refusal=None,
        blocked_reason=None,
        response_id="response-1",
        model_id="model-a",
    )
    assert receipt.text is None
    assert RawGenerationReceipt(text="").text == ""
    assert receipt.tool_calls[0].arguments.raw_text_value == "{not json"
    assert receipt.tool_calls[0].arguments.structured_value is None
    assert receipt.tool_calls[1].arguments.structured_value == {"key": [1, None]}
    with pytest.raises(FrozenInstanceError):
        attribute = "text"
        setattr(receipt, attribute, "replacement")


def test_request_rejects_unknown_objects_instead_of_stringifying_them() -> None:
    class SDKObject:
        pass

    with pytest.raises(TypeError):
        GenerationRequest.create(
            "system",
            [{"role": "user", "content": SDKObject()}],
            contract=ResponseContract("payload", "v1", Payload),
            provider="openrouter",
            model="model-a",
            destination_fingerprint="destination-a",
            role="memory_summary",
            logical_result_id="result-1",
            output_limit=OutputLimit(60000),
        )


def test_request_binds_provider_inputs_and_derives_prefix_hash() -> None:
    tools: list[dict[str, object]] = [{"type": "function", "function": {"name": "move"}}]
    effective_schema: dict[str, JsonValue] = {
        "type": "object",
        "properties": {"result": {"type": "string"}},
    }
    messages: list[dict[str, object]] = [{"role": "user", "content": "start"}]
    request = GenerationRequest.create(
        "system",
        messages,
        contract=ResponseContract("payload", "v1", Payload),
        provider="openrouter",
        model="model-a",
        destination_fingerprint="destination-a",
        tool_declarations=tools,
        effective_schema=effective_schema,
        role="memory_summary",
        logical_result_id="result-1",
        output_limit=OutputLimit(60000),
    )
    tools[0]["type"] = "changed"
    assert request.identity is not None
    assert request.contract is not None
    messages[0]["content"] = "changed"
    assert request.initial_prefix_hash == request.identity.initial_prefix_hash
    assert request.messages[0]["content"] == "start"
    assert request.identity.model == "model-a"
    assert request.contract.name == "payload"
    assert request.tool_declarations[0]["type"] == "function"
    assert request.identity.tool_declarations_hash != make_identity().tool_declarations_hash
    assert request.canonical_schema == effective_schema
    assert request.identity.effective_schema_hash != make_identity().effective_schema_hash


def test_request_accepts_an_effective_wire_schema_and_hashes_it() -> None:
    effective_schema: dict[str, JsonValue] = {
        "type": "object",
        "properties": {"result": {"type": "string", "enum": ["approved"]}},
        "required": ["result"],
        "additionalProperties": False,
    }
    request = make_request(
        wire_model=OtherWirePayload,
        effective_schema=effective_schema,
        wire_schema=effective_schema,
    )
    assert request.wire_schema == effective_schema
    assert request.canonical_schema == effective_schema
    assert request.identity.wire_schema_hash != make_identity().wire_schema_hash


def test_policy_enriched_schema_is_the_default_wire_schema_without_a_wire_model() -> None:
    effective_schema: dict[str, JsonValue] = {
        "type": "object",
        "properties": {"result": {"type": "string", "enum": ["approved"]}},
        "required": ["result"],
        "additionalProperties": False,
    }
    request = make_request(effective_schema=effective_schema)
    assert request.wire_schema == effective_schema


def test_policy_enriched_canonical_schema_requires_explicit_wire_encoding() -> None:
    effective_schema: dict[str, JsonValue] = {
        "type": "object",
        "properties": {"result": {"type": "string", "enum": ["approved"]}},
        "required": ["result"],
        "additionalProperties": False,
    }
    with pytest.raises(ValueError, match="effective wire schema"):
        make_request(wire_model=OtherWirePayload, effective_schema=effective_schema)


def test_request_identity_is_derived_from_frozen_request_after_replace() -> None:
    base = make_request()
    assert replace(base, model="model-b").identity.digest != base.identity.digest
    assert replace(base, role="npc").identity.digest != base.identity.digest
    assert (
        replace(base, contract=ResponseContract("payload", "v2", Payload)).identity.digest
        != base.identity.digest
    )
    assert replace(base, system_prompt="changed").identity.initial_prefix_hash != (
        base.identity.initial_prefix_hash
    )
    assert replace(base, output_limit=OutputLimit(50000)).identity.digest != base.identity.digest
    changed_schema = replace(base, _effective_schema_json=json.dumps({"type": "string"}))
    assert changed_schema.identity.digest != base.identity.digest
    assert base.identity.role == "memory_summary"
    assert base.identity.logical_result_id == "result-1"


def test_derived_request_changes_only_messages_and_explicit_format_mode() -> None:
    base = GenerationRequest.create(
        "system",
        [
            {
                "role": "assistant",
                "content": None,
                TEXT_SIGNATURE_KEY: b"google-root-signature",
                TOOL_CALL_SIGNATURES_KEY: {"call-2": b"sig-2", "call-1": b"sig-1"},
                "tool_calls": [
                    {"id": "call-2", "function": {"arguments": '{"z":1,"a":2}'}},
                    {"id": "call-1", "function": {"arguments": "{malformed"}},
                ],
            },
            {"role": "user", "content": "original"},
        ],
        contract=ResponseContract("payload", "v1", Payload),
        provider="google",
        model="model-a",
        destination_fingerprint="destination-a",
        wire_model=WirePayload,
        wire_schema=WirePayload.model_json_schema(),
        effective_schema={
            "type": "object",
            "properties": {"result": {"type": "string"}, "policy": {"const": "frozen"}},
        },
        role="dm_response",
        logical_result_id="result-1",
        output_limit=OutputLimit(60000),
        allow_json_mode_fallback=True,
        allow_prompt_only_fallback=True,
        session_affinity="session-1",
    )
    original_messages = base.messages
    messages: list[dict[str, object]] = [
        *original_messages,
        {"role": "user", "content": "correction"},
    ]

    derived = base.derive(messages=messages)
    json_mode = base.derive(messages=messages, format_mode=FormatMode.JSON_MODE)

    assert base.messages == original_messages
    assert derived.messages == messages
    assert derived.system_prompt == base.system_prompt
    assert derived.identity.digest != base.identity.digest
    assert derived.identity.format_mode is base.identity.format_mode
    assert derived.identity.provider == base.identity.provider
    assert derived.identity.model == base.identity.model
    assert derived.identity.output_limit == base.identity.output_limit
    assert derived.wire_schema == base.wire_schema
    assert derived.canonical_schema == base.canonical_schema
    assert derived.identity.allow_json_mode_fallback
    assert derived.identity.allow_prompt_only_fallback
    assert derived.identity.session_affinity == "session-1"
    assert json_mode.identity.format_mode is FormatMode.JSON_MODE
    assert json_mode.identity.digest != derived.identity.digest
    assert base.identity.format_mode is FormatMode.STRICT_NATIVE
    assert base.messages[0][TEXT_SIGNATURE_KEY] == b"google-root-signature"
    assert cast(dict[str, bytes], base.messages[0][TOOL_CALL_SIGNATURES_KEY]) == {
        "call-2": b"sig-2",
        "call-1": b"sig-1",
    }
    assert cast(list[dict[str, object]], base.messages[0]["tool_calls"])[0]["id"] == "call-2"

    with pytest.raises(TypeError):
        cast(Callable[..., GenerationRequest], base.derive)(messages=messages, provider="openai")
    with pytest.raises(ValueError, match="not authorized"):
        make_request().derive(messages=messages, format_mode=FormatMode.JSON_MODE)


def test_request_requires_explicit_result_identity_and_output_limit() -> None:
    with pytest.raises(TypeError):
        cast(Callable[..., GenerationRequest], GenerationRequest.create)(
            "system",
            [],
            contract=ResponseContract("payload", "v1", Payload),
            provider="openrouter",
            model="model-a",
            destination_fingerprint="destination-a",
        )


def test_request_preserves_absent_null_and_marker_shaped_root_metadata() -> None:
    marker = {"encoding_version": 1, "base64": "c2ln"}
    request = make_request(
        messages=[
            {"role": "user"},
            {"role": "assistant", TEXT_SIGNATURE_KEY: None, TOOL_CALL_SIGNATURES_KEY: None},
            {"role": "assistant", TEXT_SIGNATURE_KEY: marker},
            {"role": "assistant", TOOL_CALL_SIGNATURES_KEY: {"call": marker}},
            {"role": "user", "content": {"nested": marker}},
        ]
    )
    messages = request.messages
    assert TEXT_SIGNATURE_KEY not in messages[0]
    assert messages[1][TEXT_SIGNATURE_KEY] is None
    assert messages[1][TOOL_CALL_SIGNATURES_KEY] is None
    assert messages[2][TEXT_SIGNATURE_KEY] == marker
    assert messages[3][TOOL_CALL_SIGNATURES_KEY] == {"call": marker}
    assert messages[4]["content"] == {"nested": marker}


def test_request_rejects_bytes_outside_known_root_signature_metadata() -> None:
    for messages in (
        [{"role": "user", "content": b"not-json"}],
        [{"role": "assistant", TOOL_CALL_SIGNATURES_KEY: {"call": {"nested": b"bad"}}}],
    ):
        with pytest.raises(TypeError):
            make_request(messages=messages)


def test_request_identity_tracks_explicit_effective_schema_snapshot() -> None:
    contract = ResponseContract("payload", "v1", Payload)
    schema: dict[str, JsonValue] = {
        "type": "object",
        "properties": {"result": {"type": "string"}, "policy": {"const": "strict"}},
    }
    request = make_request(contract=contract, effective_schema=schema)
    schema["properties"] = {}
    assert request.canonical_schema["properties"] == {
        "result": {"type": "string"},
        "policy": {"const": "strict"},
    }
    assert (
        request.identity.effective_schema_hash
        != make_request(contract=contract).identity.effective_schema_hash
    )
    assert make_request(contract=contract, effective_schema={}).canonical_schema == {}


def test_google_signature_encoding_is_root_metadata_only_and_versioned() -> None:
    request = GenerationRequest.create(
        "system",
        [
            {
                "role": "assistant",
                TEXT_SIGNATURE_KEY: b"sig",
                TOOL_CALL_SIGNATURES_KEY: {"call": b"call-sig"},
                "content": {"$generation_bytes_base64": "user-data"},
                "tool_calls": [
                    {"function": {"arguments": {"$generation_bytes_base64": "argument"}}}
                ],
            }
        ],
        contract=ResponseContract("payload", "v1", Payload),
        provider="openrouter",
        model="model-a",
        destination_fingerprint="destination-a",
        role="memory_summary",
        logical_result_id="result-1",
        output_limit=OutputLimit(60000),
    )
    message = request.messages[0]
    assert message[TEXT_SIGNATURE_KEY] == b"sig"
    assert cast(dict[str, bytes], message[TOOL_CALL_SIGNATURES_KEY])["call"] == b"call-sig"
    assert message["content"] == {"$generation_bytes_base64": "user-data"}
    calls = cast(list[dict[str, object]], message["tool_calls"])
    arguments = cast(dict[str, object], cast(dict[str, object], calls[0]["function"])["arguments"])
    assert arguments == {"$generation_bytes_base64": "argument"}
    assert '"encoding_version"' in request.snapshot_json


def test_structured_tool_arguments_reject_bytes() -> None:
    with pytest.raises(TypeError):
        RawToolArguments.structured({"argument": b"not JSON"})


def test_receipt_preserves_complete_unknown_candidate_in_original_order() -> None:
    raw = '{"parts":[{"text":"before"},{"unknown":{"x":1}},{"function_call":{"name":"f"}},{"text":"after"}]}'
    receipt = RawGenerationReceipt(text="beforeafter", raw_candidate=raw)
    assert receipt.raw_candidate == raw


def test_known_output_limit_can_exceed_ceiling_and_is_capped() -> None:
    assert OutputLimit(60000, 90000, "provider metadata").effective == 60000
