import json

import pytest

from app.ai.generation_contracts import RawGenerationReceipt
from app.ai.generation_execution_ledger import GenerationRecoveryPolicy
from app.ai.npc_director import invoke_single_npc
from app.ai.npc_generation import build_npc_generation_request
from app.ai.npc_outcomes import (
    NPC_RESPONSE_CONTRACT,
    NPCSpeaking,
    npc_response_schema,
    parse_actor_result,
)
from app.ai.response_validation import DiagnosticCode, ResponseValidationError
from app.ai.router import ModelConfig
from app.core.psychology import DEFAULT_PSYCHOLOGY
from tests.unit.eval.dialogue.typed_provider_test_support import TypedResponseProvider


def configure_provider(monkeypatch, provider: TypedResponseProvider) -> None:
    monkeypatch.setattr(
        "app.ai.npc_director.get_generation",
        lambda: _resolved_provider(provider),
    )
    monkeypatch.setattr(
        "app.ai.npc_director.get_generation_recovery_policy",
        lambda: GenerationRecoveryPolicy(1),
    )


async def _resolved_provider(provider: TypedResponseProvider):
    return provider, ModelConfig(
        "local",
        "test",
        60000,
        destination_fingerprint="offline-test-destination",
    )


@pytest.mark.parametrize(
    "raw",
    [
        '{"action":"Looks away.","axis_changes":{"trust":5}}',
        '{"status":"speaking","lines":[]}',
        '{"status":"speaking","lines":["", "...", "…", "   "]}',
        '{"status":"silent","lines":["Not silent"]}',
        '{"status":"speaking","lines":"hello"}',
        '{"status":"speaking","lines":[42]}',
        "[]",
        "null",
        '{"status":"silent","action":42}',
        '{"status":"speaking","lines":["hello [[npc:Lyra:1]]"]}',
        '{"status":"speaking","lines":["hello"],"action":"[[npc:Lyra:"}',
        '{"status":"silent","action":"[[NPC"}',
    ],
)
async def test_unusable_actor_output_is_failure_not_a_conversation(monkeypatch, raw):
    provider = TypedResponseProvider([RawGenerationReceipt(text=raw)])
    configure_provider(monkeypatch, provider)
    result = await invoke_single_npc("Lyra", {"name": "Lyra"}, "Hello", "A clearing.")
    assert getattr(result, "status", None) == "failure"
    assert not getattr(result, "lines", ())
    assert not getattr(result, "axis_changes", {})
    assert len(provider.requests) == 1


async def test_speaking_keeps_verbatim_lines_and_configured_cap(monkeypatch):
    provider = TypedResponseProvider(
        [
            RawGenerationReceipt(
                text=json.dumps(
                    {
                        "status": "speaking",
                        "lines": ["  First.  ", "Second."],
                        "action": "[a gesture]",
                        "axis_changes": [{"key": "trust", "value": 3}],
                        "reveals_secret": False,
                    }
                )
            )
        ]
    )
    monkeypatch.setenv("SAGA_GAMEPLAY_NPC_MAX_LINES", "2")
    configure_provider(monkeypatch, provider)
    result = await invoke_single_npc("Lyra", {"name": "Lyra"}, "Hello", "A clearing.")
    assert getattr(result, "status", None) == "speaking"
    assert result.lines == ("  First.  ", "Second.")
    assert result.action == "[a gesture]"
    assert result.axis_changes == {"trust": 3}
    assert provider.requests[0].output_limit.effective == 60000


async def test_explicit_silence_is_a_valid_actor_choice(monkeypatch):
    provider = TypedResponseProvider(
        [
            RawGenerationReceipt(
                text=json.dumps(
                    {
                        "status": "silent",
                        "lines": [],
                        "action": "Prepares to strike.",
                        "axis_changes": [{"key": "fear", "value": 2}],
                        "reveals_secret": False,
                    }
                )
            )
        ]
    )
    configure_provider(monkeypatch, provider)
    result = await invoke_single_npc("Lyra", {"name": "Lyra"}, "Hello", "A clearing.")
    assert getattr(result, "status", None) == "silent"
    assert result.lines == ()
    assert result.axis_changes == {"fear": 2}


@pytest.mark.parametrize(
    "data",
    [
        {"status": "speaking", "lines": ["Hello."], "axis_changes": {"trust": 1.5}},
        {"status": "speaking", "lines": ["Hello."], "axis_changes": {"trust": True}},
        {"status": "speaking", "lines": ["Hello."], "axis_changes": {"unknown": 1}},
        {"status": "speaking", "lines": ["Hello.", "Again."]},
        {"status": "speaking", "lines": ["", "..."]},
        {"status": "silent", "lines": ["Not silent"]},
        {"status": "speaking", "lines": ["Hello [[npc:Lyra:1]]"]},
        {"status": "speaking", "lines": ["Hello."], "unexpected": True},
    ],
)
def test_npc_response_contract_rejects_invalid_output(data: dict[str, object]) -> None:
    with pytest.raises(ResponseValidationError):
        parse_actor_result("Lyra", data, 1, DEFAULT_PSYCHOLOGY)


def test_npc_response_contract_preserves_valid_lines_and_changes() -> None:
    result = parse_actor_result(
        "Lyra",
        {
            "status": "speaking",
            "lines": ["First.", "Second."],
            "axis_changes": {"trust": 3},
        },
        2,
        DEFAULT_PSYCHOLOGY,
    )
    assert result == NPCSpeaking("Lyra", ("First.", "Second."), axis_changes={"trust": 3})


def test_npc_schema_enriches_canonical_axis_map_from_world_definition() -> None:
    schema = npc_response_schema(DEFAULT_PSYCHOLOGY)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    axis_changes = properties["axis_changes"]
    assert isinstance(axis_changes, dict)
    axes = axis_changes["properties"]
    assert isinstance(axes, dict)
    assert set(axes) == set(DEFAULT_PSYCHOLOGY.axes)
    assert axis_changes["additionalProperties"] is False


def test_valid_delta_remains_subject_to_existing_gameplay_clamp() -> None:
    from app.core.dm.npc_results import apply_actor_effects

    result = parse_actor_result(
        "Lyra",
        {"status": "speaking", "lines": ["The truth."], "axis_changes": {"trust": 80}},
        1,
        DEFAULT_PSYCHOLOGY,
    )
    assert isinstance(result, NPCSpeaking)
    world_state, _ = apply_actor_effects(
        "lyra-id",
        result,
        {"npcs": {"lyra-id": {"name": "Lyra", "met_player": True}}},
        {},
        {},
    )
    assert world_state["npcs"]["lyra-id"]["psychology"]["trust"] == 10


def test_npc_request_uses_resolved_destination_and_canonical_axis_schema() -> None:
    request = build_npc_generation_request(
        system_prompt="system",
        prompt="actor prompt",
        config=ModelConfig(
            "openai",
            "gpt-4o-mini",
            300,
            allow_json_mode_fallback=True,
            destination_fingerprint="destination-v1",
        ),
        logical_result_id="actor-1",
        psychology=DEFAULT_PSYCHOLOGY,
    )

    assert request.contract is NPC_RESPONSE_CONTRACT
    assert request.provider == "openai"
    assert request.model == "gpt-4o-mini"
    assert request.destination_fingerprint == "destination-v1"
    assert request.role == "actor"
    assert request.logical_result_id == "actor-1"
    assert request.output_limit.effective == 300
    assert request.allow_json_mode_fallback
    assert request.canonical_schema == npc_response_schema(DEFAULT_PSYCHOLOGY)
    assert request.wire_encoding_version == "npc-axis-entries-v1"
    properties = request.wire_schema["properties"]
    assert isinstance(properties, dict)
    axis_changes = properties["axis_changes"]
    assert isinstance(axis_changes, dict)
    assert axis_changes["type"] == "array"
    assert request.messages == [{"role": "user", "content": "actor prompt"}]


def test_contextual_contract_failures_use_typed_diagnostics() -> None:
    with pytest.raises(ResponseValidationError) as error:
        parse_actor_result("Lyra", '{"status":"speaking","lines":["..."]}', 1)
    assert error.value.diagnostics[0].code is DiagnosticCode.VALIDATION_FAILED


async def test_actor_prompt_keeps_distinct_inputs_and_bounded_narrative(monkeypatch):
    from app.ai.prompts.npc import build_npc_prompt

    monkeypatch.setenv("SAGA_GAMEPLAY_NPC_NARRATIVE_MAX_CHARS", "1000")
    action = "PLAYER ACTION " + "x" * 1100
    context = "INVOCATION CONTEXT " + "z" * 1100
    prompt = build_npc_prompt(
        {"name": "Lyra"},
        player_action=action,
        invocation_context=context,
        dm_narration="old" * 500 + "TAIL" * 250,
        observed_beats="Public earlier beat.",
    )
    assert action in prompt and context in prompt
    assert "TAIL" * 250 in prompt and "old" * 200 not in prompt
    assert "Public earlier beat." in prompt
