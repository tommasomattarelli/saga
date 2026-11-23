from __future__ import annotations

import json
from typing import cast

import pytest
from google.genai import types

from app.ai.generation_contracts import (
    FormatMode,
    GenerationRequest,
    GenerationToolReceipt,
    OutputLimit,
    RawGenerationReceipt,
    RawToolArguments,
)
from app.ai.response_validation import Normalization, ResponseValidationError
from app.ai.router import ModelConfig
from app.ai.tools.dm_tools import get_tool
from app.core.dm.dm_generation import (
    DM_NARRATIVE_CONTRACT,
    DMNarrative,
    build_dm_generation_request,
    canonical_tool_arguments,
    dm_response_validator,
    generation_tool_declarations,
    validate_dm_narrative,
)


def _request(
    *,
    messages: list[dict[str, object]] | None = None,
    allowed_tools: set[str] | None = None,
) -> GenerationRequest:
    config = ModelConfig(
        provider="openai",
        model="gpt-test",
        max_tokens=1200,
        allow_json_mode_fallback=True,
        allow_prompt_only_fallback=False,
        destination_fingerprint="openai:destination",
    )
    return build_dm_generation_request(
        "You are the DM.",
        messages if messages is not None else [{"role": "user", "content": "Look around."}],
        config=config,
        allowed_tools=allowed_tools or set(),
        campaign_id="campaign-1",
        player_action="Look around.",
        step=2,
        previous_head_turn_id="turn-4",
        session_affinity="campaign-1",
    )


def _schema_function(schema: dict[str, object]) -> dict[str, object]:
    function = schema["function"]
    assert isinstance(function, dict)
    return cast(dict[str, object], function)


def _schema_name(schema: dict[str, object]) -> str:
    name = _schema_function(schema)["name"]
    assert isinstance(name, str)
    return name


def _tool_call(arguments: RawToolArguments | None = None) -> GenerationToolReceipt:
    return GenerationToolReceipt(
        call_id="call-1",
        name="request_dice",
        arguments=arguments or RawToolArguments.structured({"stat": "DEX"}),
    )


def test_canonical_nonwire_tool_arguments_keep_presence_and_explicit_defaults() -> None:
    request = _request(allowed_tools={"update_quest"})
    omitted = GenerationToolReceipt(
        call_id="omitted",
        name="update_quest",
        arguments=RawToolArguments.structured({"quest_id": "sealed_key", "status": "completed"}),
    )
    explicit = GenerationToolReceipt(
        call_id="explicit",
        name="update_quest",
        arguments=RawToolArguments.structured(
            {
                "quest_id": "sealed_key",
                "status": "completed",
                "name": "",
                "description": None,
            }
        ),
    )

    assert canonical_tool_arguments(omitted, request) == {
        "quest_id": "sealed_key",
        "status": "completed",
    }
    assert canonical_tool_arguments(explicit, request) == {
        "quest_id": "sealed_key",
        "status": "completed",
        "name": "",
        "description": None,
    }


def test_canonical_wire_tool_arguments_keep_presence_and_canonical_map_values() -> None:
    request = _request(allowed_tools={"update_npc"})
    omitted = GenerationToolReceipt(
        call_id="omitted",
        name="update_npc",
        arguments=RawToolArguments.structured(
            {
                "name": "Mira",
                "updates": [{"key": "condition", "value": "wounded"}],
            }
        ),
    )
    explicit = GenerationToolReceipt(
        call_id="explicit",
        name="update_npc",
        arguments=RawToolArguments.structured(
            {
                "name": "Mira",
                "updates": [{"key": "condition", "value": "wounded"}],
                "create": False,
            }
        ),
    )

    assert canonical_tool_arguments(omitted, request) == {
        "name": "Mira",
        "updates": {"condition": "wounded"},
    }
    assert canonical_tool_arguments(explicit, request) == {
        "name": "Mira",
        "updates": {"condition": "wounded"},
        "create": False,
    }


def test_generation_tool_declarations_are_selected_and_sorted() -> None:
    schemas = generation_tool_declarations({"set_scene_mood", "not_registered", "advance_time"})

    assert [_schema_name(schema) for schema in schemas] == ["advance_time", "set_scene_mood"]
    assert all(get_tool(_schema_name(schema)) is not None for schema in schemas)


def test_dm_request_freezes_real_inputs_and_prompt_only_tool_declarations() -> None:
    messages: list[dict[str, object]] = [{"role": "user", "content": "Look around."}]
    request = _request(messages=messages, allowed_tools={"request_dice"})
    messages[0]["content"] = "changed after construction"

    assert request.system_prompt == "You are the DM."
    assert request.messages == [{"role": "user", "content": "Look around."}]
    assert request.contract is DM_NARRATIVE_CONTRACT
    assert request.provider == "openai"
    assert request.model == "gpt-test"
    assert request.destination_fingerprint == "openai:destination"
    assert request.role == "dm"
    assert request.output_limit == OutputLimit(1200)
    assert request.format_mode is FormatMode.PROMPT_ONLY
    assert request.allow_json_mode_fallback is True
    assert request.allow_prompt_only_fallback is False
    assert request.session_affinity == "campaign-1"
    assert [_schema_name(item) for item in request.tool_declarations] == ["request_dice"]


def test_dm_request_without_tools_stays_native_strict() -> None:
    assert _request().format_mode is FormatMode.STRICT_NATIVE


def test_dm_logical_result_id_is_stable_per_real_step_inputs() -> None:
    first = _request()
    replay = _request()
    next_step = build_dm_generation_request(
        "You are the DM.",
        [{"role": "user", "content": "Look around."}],
        config=ModelConfig(
            provider="openai",
            model="gpt-test",
            max_tokens=1200,
            destination_fingerprint="openai:destination",
        ),
        allowed_tools=set(),
        campaign_id="campaign-1",
        player_action="Look around.",
        step=3,
        previous_head_turn_id="turn-4",
        session_affinity="campaign-1",
    )

    assert first.logical_result_id == replay.logical_result_id
    assert first.logical_result_id != next_step.logical_result_id


def test_dm_request_carries_prompt_schema_and_tools_for_google_offline() -> None:
    from app.ai.providers.google_generation import _config

    request = _request(allowed_tools={"request_dice"})

    config = _config(request)

    assert config.response_mime_type is None
    assert config.response_json_schema is None
    canonical = json.dumps(request.canonical_schema, ensure_ascii=False, separators=(",", ":"))
    assert canonical in cast(str, config.system_instruction)
    assert config.tools is not None
    tools = cast(list[types.Tool], config.tools)
    declarations = cast(list[types.FunctionDeclaration], tools[0].function_declarations)
    assert declarations[0].name == "request_dice"


def test_dm_narrative_contract_is_typed_and_closed() -> None:
    assert DM_NARRATIVE_CONTRACT.model_type is DMNarrative
    assert DM_NARRATIVE_CONTRACT.schema["additionalProperties"] is False
    assert DM_NARRATIVE_CONTRACT.schema["required"] == ["text"]
    properties = cast(dict[str, object], DM_NARRATIVE_CONTRACT.schema["properties"])
    text_schema = cast(dict[str, object], properties["text"])
    branches = cast(list[dict[str, object]], text_schema["anyOf"])
    assert [branch["type"] for branch in branches] == ["string", "null"]


def test_text_only_dm_step_accepts_valid_typed_narration() -> None:
    result = validate_dm_narrative(RawGenerationReceipt(text='{"text":"The door opens."}'))

    assert result.model.text == "The door opens."
    assert result.normalization is Normalization.NONE


@pytest.mark.parametrize("text", [None, "", " \t\n"])
def test_text_only_dm_step_rejects_missing_or_empty_narration(text: str | None) -> None:
    with pytest.raises(ResponseValidationError) as raised:
        validate_dm_narrative(RawGenerationReceipt(text=text))

    assert [(item.code, item.path) for item in raised.value.diagnostics] == [
        ("missing", ("text",))
    ]


@pytest.mark.parametrize("text", [None, "", " \t\n"])
def test_tool_bearing_dm_step_accepts_absent_or_empty_narration(text: str | None) -> None:
    result = validate_dm_narrative(RawGenerationReceipt(text=text, tool_calls=(_tool_call(),)))

    assert result.model.text is None
    assert result.normalization is Normalization.NONE


def test_empty_typed_narration_is_only_valid_when_tools_are_present() -> None:
    raw_text = '{"text":""}'

    with pytest.raises(ResponseValidationError):
        validate_dm_narrative(RawGenerationReceipt(text=raw_text))

    result = validate_dm_narrative(RawGenerationReceipt(text=raw_text, tool_calls=(_tool_call(),)))
    assert result.model.text == ""


def test_tool_bearing_dm_step_accepts_valid_present_narration() -> None:
    result = validate_dm_narrative(
        RawGenerationReceipt(text='{"text":"The guard falls."}', tool_calls=(_tool_call(),))
    )

    assert result.model.text == "The guard falls."


@pytest.mark.parametrize("text", ["The guard falls.", '{"text":3}'])
def test_tool_bearing_dm_step_rejects_invalid_present_narration(text: str) -> None:
    with pytest.raises(ResponseValidationError):
        validate_dm_narrative(RawGenerationReceipt(text=text, tool_calls=(_tool_call(),)))


@pytest.mark.parametrize("text", ['{"text":"one","text":"two"}', '{"text":NaN}'])
def test_dm_narrative_rejects_duplicate_keys_and_nonfinite_numbers(text: str) -> None:
    with pytest.raises(ResponseValidationError) as raised:
        validate_dm_narrative(RawGenerationReceipt(text=text, tool_calls=(_tool_call(),)))

    assert [(item.code, item.path) for item in raised.value.diagnostics] == [("invalid_json", ())]


def _valid_tool_call() -> GenerationToolReceipt:
    return GenerationToolReceipt(
        call_id="call-1",
        name="request_dice",
        arguments=RawToolArguments.structured(
            {"check": "stealth", "stat": "DEX", "difficulty": "normal"}
        ),
    )


def test_prompt_only_tool_bearing_step_accepts_plain_prose() -> None:
    request = _request(allowed_tools={"request_dice"})

    result = dm_response_validator(
        RawGenerationReceipt(text="The door opens.", tool_calls=(_valid_tool_call(),)), request
    )

    assert result.model.text == "The door opens."
    assert result.normalization is Normalization.NONE


def test_prompt_only_tool_bearing_step_still_accepts_a_typed_envelope() -> None:
    request = _request(allowed_tools={"request_dice"})

    result = dm_response_validator(
        RawGenerationReceipt(text='{"text":"The door opens."}', tool_calls=(_valid_tool_call(),)),
        request,
    )

    assert result.model.text == "The door opens."


@pytest.mark.parametrize(
    "text",
    ['{"text":"one","text":"two"}', '{"text":NaN}', "```json\nplain prose\n```"],
)
def test_prompt_only_tool_bearing_step_rejects_malformed_envelopes(text: str) -> None:
    request = _request(allowed_tools={"request_dice"})

    with pytest.raises(ResponseValidationError):
        dm_response_validator(
            RawGenerationReceipt(text=text, tool_calls=(_valid_tool_call(),)), request
        )


def test_prompt_only_tool_bearing_step_still_rejects_unregistered_tool() -> None:
    request = _request(allowed_tools={"request_dice"})
    call = GenerationToolReceipt(
        call_id="call-1",
        name="not_registered",
        arguments=RawToolArguments.structured({"check": "stealth"}),
    )

    with pytest.raises(ResponseValidationError):
        dm_response_validator(
            RawGenerationReceipt(text="The door opens.", tool_calls=(call,)), request
        )


def test_native_strict_tool_bearing_step_still_rejects_plain_prose() -> None:
    base = _request(allowed_tools={"request_dice"})
    request = base.derive(messages=base.messages, format_mode=FormatMode.STRICT_NATIVE)

    with pytest.raises(ResponseValidationError):
        dm_response_validator(
            RawGenerationReceipt(text="The door opens.", tool_calls=(_valid_tool_call(),)), request
        )


def test_narrative_validation_preserves_raw_tool_argument_receipt() -> None:
    raw_arguments = RawToolArguments.raw_text('{"stat":1,"stat":2}')
    call = _tool_call(raw_arguments)

    validate_dm_narrative(RawGenerationReceipt(text="", tool_calls=(call,)))

    assert call.arguments.raw_text_value == '{"stat":1,"stat":2}'
