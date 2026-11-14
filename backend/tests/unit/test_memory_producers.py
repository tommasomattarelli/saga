import json
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.ai.router import ModelConfig
from app.memory.batch_source_contracts import BatchInput
from app.memory.document_contracts import GlobalPayload
from app.memory.producer_contracts import MemoryOutputError
from app.memory.producer_prompts import PreparedMemoryRequest, ProducerKind, prepare_request
from app.memory.producers import generate_memory
from app.memory.production_policy import FactsPolicy, GlobalPolicy


def facts_policy(*, cap: int = 4) -> FactsPolicy:
    return FactsPolicy.model_validate(
        {
            "max_per_batch": cap,
            "importance_levels": [
                {"name": "major", "criteria": "Changes the campaign", "examples": "A betrayal"},
                {"name": "minor", "criteria": "Adds color", "examples": "A shared meal"},
            ],
        }
    )


def source(
    *,
    action: str = "Ask Mira about the key",
    narration: str = "Mira hid the key.",
    operations=True,
) -> BatchInput:
    operation = {
        "id": uuid4(),
        "ordinal": 1,
        "step": None,
        "beat": None,
        "payload": {
            "origin": "npc",
            "name": "create_npc",
            "outcome": "succeeded",
            "arguments": {"name": "Mira"},
            "result": {
                "kind": "npc",
                "npc_id": "npc-mira",
                "status": "created",
                "action": None,
                "axis_changes": {},
            },
            "deltas": [],
        },
    }
    return BatchInput.model_validate_json(
        json.dumps(
            {
                "turns": [
                    {
                        "reference": "t1",
                        "turn_id": uuid4(),
                        "player_action": action,
                        "narration": narration,
                        "operations": [operation] if operations else None,
                    }
                ]
            },
            default=str,
        )
    )


def request(
    kind: ProducerKind,
    batch: BatchInput | None = None,
    *,
    global_policy: GlobalPolicy | None = None,
    previous: GlobalPayload | None = None,
) -> PreparedMemoryRequest:
    return prepare_request(
        kind,
        batch or source(),
        language="it",
        facts_policy=facts_policy(),
        global_policy=global_policy,
        previous=previous,
    )


def schema_object(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def test_global_request_contains_full_previous_state_and_original_batch() -> None:
    previous = GlobalPayload(
        story_so_far="The party reached the drowned city.",
        open_threads=("Who rang the bell?",),
        relationships=("Mira distrusts Oren.",),
        resolved_threads=("The key was found.",),
    )
    batch = source()
    prepared = request(
        "global", batch, global_policy=GlobalPolicy(target_words=237), previous=previous
    )
    for value in (
        previous.story_so_far,
        *previous.open_threads,
        *previous.relationships,
        *previous.resolved_threads,
        batch.turns[0].player_action,
        batch.turns[0].narration,
        "237",
    ):
        assert value in prepared.user_prompt
    with pytest.raises(ValueError):
        request("global", batch, previous=previous)


def test_output_validation_rejects_wrong_shapes_and_accepts_empty_facts() -> None:
    facts = request("facts")
    facts.validate_output('{"facts":[]}')
    invalid = (
        '{"facts":[],"unexpected":true}',
        '{"facts":[{"content":"x"}]}',
        json.dumps(
            {
                "facts": [
                    {
                        "content": "x",
                        "category": "event",
                        "assertion_type": "occurrence",
                        "entities": [],
                        "attribution": [],
                        "source_turns": ["t1"],
                        "temporal_references": [],
                        "importance": {"level": "major", "reason": "reason"},
                    }
                ]
                * 5
            }
        ),
    )
    for raw in invalid:
        with pytest.raises((ValueError, TypeError)):
            facts.validate_output(raw)


def test_global_output_requires_exact_four_field_schema() -> None:
    global_request = request("global", global_policy=GlobalPolicy(target_words=100))
    valid = {
        "story_so_far": "The party reached the city.",
        "open_threads": [],
        "relationships": [],
        "resolved_threads": [],
    }
    global_request.validate_output(json.dumps(valid))
    for raw in (
        json.dumps({**valid, "unexpected": "field"}),
        json.dumps({key: value for key, value in valid.items() if key != "resolved_threads"}),
    ):
        with pytest.raises((ValueError, TypeError)):
            global_request.validate_output(raw)


def test_output_validation_rejects_fences_duplicate_keys_and_non_finite_numbers() -> None:
    facts = request("facts")
    for raw in (
        '```json\n{"facts":[]}\n```',
        '{"facts":[],"facts":[]}',
        '{"facts":[],"extra":NaN}',
    ):
        with pytest.raises((ValueError, TypeError)):
            facts.validate_output(raw)


def test_global_source_hash_includes_previous_payload() -> None:
    first_previous = GlobalPayload(
        story_so_far="The party reached the drowned city.",
        open_threads=("Who rang the bell?",),
        relationships=("Mira distrusts Oren.",),
        resolved_threads=("The key was found.",),
    )
    changed_previous = first_previous.model_copy(
        update={"story_so_far": "The party entered the drowned city."}
    )
    batch = source()
    first = request(
        "global", batch, global_policy=GlobalPolicy(target_words=100), previous=first_previous
    )
    changed = request(
        "global", batch, global_policy=GlobalPolicy(target_words=100), previous=changed_previous
    )
    assert first.source_hash != changed.source_hash
    assert first.instruction_hash == changed.instruction_hash


def test_global_request_rejects_duplicate_source_references() -> None:
    batch = source()
    duplicate = BatchInput.model_validate_json(
        json.dumps(
            {
                "turns": [
                    batch.turns[0].model_dump(mode="json"),
                    {**batch.turns[0].model_dump(mode="json"), "turn_id": str(uuid4())},
                ]
            }
        )
    )
    with pytest.raises(ValueError):
        request("global", duplicate, global_policy=GlobalPolicy(target_words=100))


@pytest.mark.asyncio
async def test_generation_uses_one_plain_generate_with_router_config_and_propagates_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.memory import producers
    from app.memory.producer_prompts import canonical

    provider = Mock()
    config = ModelConfig(provider="local", model="unit-model", max_tokens=731)
    get_generation = AsyncMock(return_value=(provider, config))
    logged_generate = AsyncMock(return_value='{"text":"A short summary."}')
    monkeypatch.setattr(producers, "get_generation", get_generation)
    monkeypatch.setattr(producers, "logged_generate", logged_generate)
    prepared = request("summary")
    result = await generate_memory(prepared)
    get_generation.assert_awaited_once_with()
    logged_generate.assert_awaited_once()
    args = logged_generate.await_args
    assert args is not None
    assert args.kwargs["system_prompt"] == prepared.system_prompt
    assert canonical(prepared.response_schema) in args.kwargs["system_prompt"]
    assert args.kwargs["model"] == "unit-model"
    assert args.kwargs["max_tokens"] == 731
    assert args.kwargs["json_mode"] is True
    assert result.provider == "local"
    assert result.model == "unit-model"
    assert result.raw == '{"text":"A short summary."}'

    logged_generate.reset_mock()
    logged_generate.return_value = '{"unexpected":true}'
    with pytest.raises(MemoryOutputError):
        await generate_memory(request("summary"))
    logged_generate.assert_awaited_once()
