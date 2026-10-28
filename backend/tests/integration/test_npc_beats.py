import asyncio
import json

import pytest

from app.ai.providers.schemas import ToolCall
from tests.integration.test_quest_persistence import (
    _create_campaign,
    _openai_provider,
    _reply,
    _script,
    _take_turn,
)


def call(call_id: str, tool: str, **args: object) -> ToolCall:
    return ToolCall(id=call_id, name=tool, arguments=args)


def actor(name: str, context: str = "") -> ToolCall:
    return call(name, "invoke_npc", name=name, context=context)


def speaking(*lines: str, **extra: object) -> str:
    return json.dumps({"status": "speaking", "lines": list(lines), **extra})


@pytest.mark.parametrize("one_fails", [False, True])
async def test_a_beat_is_parallel_live_and_applied_in_call_order(
    auth_client,
    generation_clients,
    assert_no_db_held,
    one_fails,
):
    created = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    both_started = asyncio.Event()
    inputs = []

    async def generate(**kwargs):
        assert_no_db_held()
        inputs.append(kwargs)
        if len(inputs) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=2)
        if "You are Lyra," in kwargs["system_prompt"]:
            await asyncio.sleep(0)
            return speaking("Lyra first.", "Lyra second.", axis_changes={"trust": 2})
        return "{}" if one_fails else speaking("Aldric first.")

    provider.generate.side_effect = generate
    dm = _script(
        provider,
        [
            _reply(
                "The wind rises.",
                actor("Lyra", "ASK LYRA"),
                call(
                    "update",
                    "update_npc",
                    name="Aldric",
                    updates={"location": "Shrine of First Light", "condition": "recently arrived"},
                ),
                actor("Aldric", "ASK ALDRIC"),
            ),
            _reply("Between. [[npc:Lyra:1]] After. [[npc:Lyra:2]]"),
        ],
    )
    result = await _take_turn(auth_client, created["id"], "THE REAL PLAYER ACTION")
    assert len(inputs) == 2
    assert all("THE REAL PLAYER ACTION" in request["messages"][0]["content"] for request in inputs)
    aldric = next(r for r in inputs if "You are Aldric," in r["system_prompt"])
    assert "recently arrived" in aldric["messages"][0]["content"]
    assert "ASK ALDRIC" in aldric["messages"][0]["content"]
    assert "Lyra first." not in aldric["messages"][0]["content"]
    messages = [m for m in dm[1]["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in messages] == ["Lyra", "update", "Aldric"]
    parts = [p for s in result["narration_segments"] for p in s["parts"]]
    lines = [p["dialogue"] for p in parts if p["type"] == "npc_speech"]
    assert lines == ["Lyra first.", "Lyra second."] + ([] if one_fails else ["Aldric first."])
    assert result["narration"].count("Lyra first.") == 1
    assert "npc_dialogues" not in result


async def test_whole_beat_cap_dedupe_and_validation_precede_creation(
    auth_client,
    generation_clients,
    monkeypatch,
):
    monkeypatch.setenv("SAGA_GAMEPLAY_NPC_VERBOSITY", "minimal")
    created = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    provider.generate.side_effect = None
    provider.generate.return_value = speaking("Only once.")
    dm = _script(
        provider,
        [
            _reply(
                "",
                actor("Aldric"),
                actor("Lyra"),
                actor("lyra"),
                actor("New One"),
                actor("New Two"),
            ),
            _reply("A pause."),
        ],
    )
    result = await _take_turn(auth_client, created["id"])
    assert provider.generate.await_count == 1
    assert {n["name"] for n in result["world_state"]["npcs"].values()} == {
        n["name"] for n in created["world_state"]["npcs"].values()
    }
    tool_results = [m for m in dm[1]["messages"] if m["role"] == "tool"]
    assert len(tool_results) == 5
    assert [m["tool_call_id"] for m in tool_results] == [
        "Aldric",
        "Lyra",
        "lyra",
        "New One",
        "New Two",
    ]
    assert "present" in tool_results[0]["content"]
    assert "beat" in tool_results[2]["content"]
    assert "limit" in tool_results[3]["content"]


async def test_selected_auto_created_identity_survives_failure_without_effects(
    auth_client,
    generation_clients,
):
    created = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    provider.generate.side_effect = None
    provider.generate.return_value = "{}"
    _script(provider, [_reply("", actor("New Farmer")), _reply("The farmer waits.")])
    result = await _take_turn(auth_client, created["id"])
    farmer = next(n for n in result["world_state"]["npcs"].values() if n["name"] == "New Farmer")
    assert farmer["auto_created"]
    assert farmer["location"] == result["world_state"]["meta"]["current_location"]
    assert not farmer["met_player"] and not farmer["last_interactions"]
    assert result["narration"] == "The farmer waits."


async def test_duplicate_provider_ids_do_not_overwrite_independent_tool_results(
    auth_client,
    generation_clients,
    monkeypatch,
):
    monkeypatch.setenv("SAGA_GAMEPLAY_NPC_VERBOSITY", "minimal")
    created = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    provider.generate.side_effect = None
    provider.generate.return_value = speaking("A real reply.")
    requests = _script(
        provider,
        [
            _reply(
                "",
                call("same", "invoke_npc", name="Lyra"),
                call("same", "invoke_npc", name="Trimmed NPC"),
            ),
            _reply("The wind stirs."),
        ],
    )
    await _take_turn(auth_client, created["id"])
    results = [m for m in requests[1]["messages"] if m["role"] == "tool"]
    assert len(results) == 2
    assert "[[npc:Lyra:1]]" in results[0]["content"]
    assert "limit" in results[1]["content"]


async def test_later_beats_observe_all_and_only_their_public_events(
    auth_client,
    generation_clients,
):
    created = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    inputs = []

    async def generate(**kwargs):
        prompt = kwargs["messages"][0]["content"]
        inputs.append(prompt)
        return speaking(
            "UNSEEN VILLAGE WORDS"
            if "You are Aldric," in kwargs["system_prompt"]
            else "SHRINE FIRST WORDS",
            axis_changes={"trust": 1},
        )

    provider.generate.side_effect = generate
    _script(
        provider,
        [
            _reply("SHRINE SECRET PROSE", actor("Lyra")),
            _reply("", call("travel", "move_to", location="Thornhaven"), actor("Aldric")),
            _reply("", call("return", "move_to", location="Shrine of First Light"), actor("Lyra")),
            _reply("You wait. [[npc:Lyra:2]]"),
        ],
    )
    result = await _take_turn(auth_client, created["id"], "I visit each place, then return.")
    assert len(inputs) == 3
    assert "SHRINE FIRST WORDS" not in inputs[1] and "SHRINE SECRET PROSE" not in inputs[1]
    assert "UNSEEN VILLAGE WORDS" not in inputs[2]
    assert "SHRINE FIRST WORDS" in inputs[2] and "SHRINE SECRET PROSE" in inputs[2]
    assert "[[npc:Lyra" not in " ".join(inputs)
    lyra = next(n for n in result["world_state"]["npcs"].values() if n["name"] == "Lyra")
    assert len(lyra["last_interactions"]) == 1
    assert lyra["last_interactions"][0].count("SHRINE FIRST WORDS") == 2


async def test_penultimate_actor_intention_cannot_resolve_damage_in_final_step(
    auth_client,
    generation_clients,
    monkeypatch,
):
    monkeypatch.setenv("SAGA_GAMEPLAY_MAX_AGENT_STEPS", "2")
    created = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    provider.generate.side_effect = None
    provider.generate.return_value = json.dumps(
        {
            "status": "silent",
            "lines": [],
            "action": "Prepares to strike the player.",
            "axis_changes": {"fear": 1},
        }
    )
    dm = _script(
        provider,
        [
            _reply("", actor("Lyra")),
            _reply(
                "She remains poised to strike.",
                call(
                    "attack", "attack", attacker="Lyra", target=created["character_data"]["name"]
                ),
            ),
        ],
    )
    result = await _take_turn(auth_client, created["id"])
    assert len(dm) == 2
    assert result["character_data"]["hp"] == created["character_data"]["hp"]
    assert "Prepares to strike" in dm[1]["messages"][-1]["content"]
    lyra = next(n for n in result["world_state"]["npcs"].values() if n["name"] == "Lyra")
    assert lyra["met_player"] and len(lyra["last_interactions"]) == 1
    assert not [
        p for s in result["narration_segments"] for p in s["parts"] if p["type"] == "npc_speech"
    ]
