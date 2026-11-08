from unittest.mock import patch

from app.ai.providers.schemas import ToolCall
from tests.integration.gameplay.test_quest_persistence import (
    _create_campaign,
    _openai_provider,
    _reply,
    _script,
    _take_turn,
)


async def test_actor_intention_requires_a_later_real_mechanical_tool(
    auth_client,
    generation_clients,
):
    created = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    provider.generate.side_effect = None
    provider.generate.return_value = (
        '{"status":"silent","lines":[],"action":"Prepares to strike the player."}'
    )
    requests = _script(
        provider,
        [
            _reply("", ToolCall("npc", "invoke_npc", {"name": "Lyra"})),
            _reply(
                "She attempts the strike.",
                ToolCall(
                    "hit",
                    "attack",
                    {"attacker": "Lyra", "target": created["character_data"]["name"]},
                ),
            ),
            _reply("The strike lands."),
        ],
    )
    with patch(
        "app.core.dice.random.randint", side_effect=lambda low, high: high if high == 20 else low
    ):
        result = await _take_turn(auth_client, created["id"], "I threaten Lyra.")
    assert len(requests) == 3 and provider.generate.await_count == 1
    assert "Prepares to strike" in requests[1]["messages"][-1]["content"]
    assert result["character_data"]["hp"]["current"] < created["character_data"]["hp"]["current"]
    assert result["tool_events"][0]["tool"] == "attack"
    assert "The strike lands." in result["narration"]


async def test_produced_line_renders_after_the_actor_dies_and_an_unknown_marker_is_removed(
    auth_client,
    generation_clients,
):
    created = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    provider.generate.side_effect = None
    provider.generate.return_value = '{"status":"speaking","lines":["A final warning."]}'
    _script(
        provider,
        [
            _reply("", ToolCall("npc", "invoke_npc", {"name": "Lyra"})),
            _reply(
                "", ToolCall("death", "kill_npc", {"name": "Lyra", "cause": "A falling tree."})
            ),
            _reply("Her warning lingers. [[npc:Lyra:1]] [[npc:Unknown:1]]"),
        ],
    )
    result = await _take_turn(auth_client, created["id"])
    lyra = next(n for n in result["world_state"]["npcs"].values() if n["name"] == "Lyra")
    assert lyra["lifecycle"] == "dead"
    assert result["narration"].count("A final warning.") == 1
    assert "[[npc" not in result["narration"]
    speech = [
        p for s in result["narration_segments"] for p in s["parts"] if p["type"] == "npc_speech"
    ]
    assert len(speech) == 1 and speech[0]["npc_name"] == "Lyra"
