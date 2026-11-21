from __future__ import annotations

import json
from typing import cast

import pytest

from app.ai.generation_contracts import FormatMode, RawGenerationReceipt
from app.ai.npc_generation import (
    _wire_contract,
    build_npc_generation_request,
    validate_npc_response,
)
from app.ai.npc_outcomes import NPCSpeaking
from app.ai.response_validation import ResponseValidationError
from app.ai.router import ModelConfig
from app.core.psychology import DEFAULT_PSYCHOLOGY
from tests.unit.ai.npc_generation_test_support import invoke_with, response
from tests.unit.eval.dialogue.typed_provider_test_support import TypedResponseProvider


def test_wire_axis_entry_types_are_derived_from_the_canonical_field() -> None:
    from typing import get_args, get_origin

    from app.ai.npc_outcomes import NPCResponse

    canonical = NPCResponse.model_fields["axis_changes"].annotation
    key_type, value_type = get_args(canonical)
    assert get_origin(canonical) is dict
    axis_names = tuple(DEFAULT_PSYCHOLOGY.axes)
    wire_fields = _wire_contract(axis_names).model_type.model_fields
    entries = get_args(wire_fields["axis_changes"].annotation)[0]
    assert entries.model_fields["key"].annotation is key_type
    assert entries.model_fields["value"].annotation is get_args(value_type)[0]
    assert tuple(entries.model_fields["value"].metadata) == get_args(value_type)[1:]
    assert entries.model_config["strict"] is True


async def test_wire_axis_enum_and_correction_guidance_follow_custom_psychology(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    psychology = DEFAULT_PSYCHOLOGY.model_copy(deep=True)
    psychology.axes = {"loyalty": psychology.axes["trust"]}
    invalid = RawGenerationReceipt(
        text=(
            '{"status":"speaking","lines":["Hello."],"action":null,'
            '"axis_changes":[{"key":"private_axis_canary","value":4}],'
            '"reveals_secret":false}'
        )
    )
    provider = TypedResponseProvider(
        [invalid, response(lines=["Corrected."], axis_changes={"loyalty": 2})]
    )
    result = await invoke_with(monkeypatch, provider, psychology=psychology, budget=2)

    assert result == NPCSpeaking("Lyra", ("Corrected.",), axis_changes={"loyalty": 2})
    request = provider.requests[0]
    properties = cast(dict[str, object], request.wire_schema["properties"])
    axis_array = cast(dict[str, object], properties["axis_changes"])
    definitions = cast(dict[str, object], request.wire_schema["$defs"])
    entry = cast(dict[str, object], definitions["NPCAxisChangeEntry"])
    entry_properties = cast(dict[str, object], entry["properties"])
    key_schema = cast(dict[str, object], entry_properties["key"])
    canonical_properties = cast(dict[str, object], request.canonical_schema["properties"])
    canonical_axis = cast(dict[str, object], canonical_properties["axis_changes"])
    assert axis_array["type"] == "array"
    assert key_schema["enum"] == ["loyalty"]
    assert list(cast(dict[str, object], canonical_axis["properties"])) == ["loyalty"]
    assert request.identity.wire_schema_hash
    guidance = cast(str, provider.requests[1].messages[-1]["content"])
    assert 'must be one of: "loyalty"' in guidance
    assert "private_axis_canary" not in guidance


@pytest.mark.parametrize(
    ("mode", "axis_changes"),
    [
        (FormatMode.STRICT_NATIVE, [{"key": "trust", "value": 2}]),
        (FormatMode.JSON_MODE, {"trust": 2}),
        (FormatMode.PROMPT_ONLY, {"trust": 2}),
    ],
)
def test_npc_mode_schema_prompt_and_validator_agree(
    mode: FormatMode, axis_changes: object
) -> None:
    from app.ai.npc_outcomes import NPC_RESPONSE_CONTRACT, npc_response_schema
    from app.ai.prompts.npc import build_npc_system_prompt

    base = build_npc_generation_request(
        system_prompt=build_npc_system_prompt(),
        prompt="Speak.",
        config=ModelConfig(
            "openai",
            "test-model",
            256,
            allow_json_mode_fallback=True,
            allow_prompt_only_fallback=True,
            destination_fingerprint="offline-test-destination",
        ),
        logical_result_id="mode-test",
        psychology=None,
    )
    request = base.derive(messages=base.messages, format_mode=mode)
    payload = json.dumps(
        {
            "status": "speaking",
            "lines": ["Hello."],
            "action": None,
            "axis_changes": axis_changes,
            "reveals_secret": False,
        }
    )

    validated = validate_npc_response(
        RawGenerationReceipt(text=payload),
        request,
        max_lines=4,
        psychology=None,
    )

    assert validated.model.axis_changes == {"trust": 2}
    assert request.contract is NPC_RESPONSE_CONTRACT
    assert request.canonical_schema == npc_response_schema(None)
    properties = cast(dict[str, object], request.wire_schema["properties"])
    axis_changes_schema = cast(dict[str, object], properties["axis_changes"])
    assert axis_changes_schema["type"] == "array"
    assert "strict native response schema is active" in request.system_prompt
    assert "JSON mode or prompt-only" in request.system_prompt
    alternate = (
        {"trust": 2} if mode is FormatMode.STRICT_NATIVE else [{"key": "trust", "value": 2}]
    )
    with pytest.raises(ResponseValidationError):
        validate_npc_response(
            RawGenerationReceipt(
                text=json.dumps(
                    {
                        "status": "speaking",
                        "lines": ["Hello."],
                        "action": None,
                        "axis_changes": alternate,
                        "reveals_secret": False,
                    }
                )
            ),
            request,
            max_lines=4,
            psychology=None,
        )


async def test_contextual_validation_runs_once_per_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = TypedResponseProvider([response(lines=["Valid."])])
    from app.ai import npc_generation

    validate = npc_generation.validate_actor_response
    calls = 0

    def count(*args, **kwargs):
        nonlocal calls
        calls += 1
        return validate(*args, **kwargs)

    monkeypatch.setattr(npc_generation, "validate_actor_response", count)
    result = await invoke_with(monkeypatch, provider)
    assert result == NPCSpeaking("Lyra", ("Valid.",))
    assert calls == 1
