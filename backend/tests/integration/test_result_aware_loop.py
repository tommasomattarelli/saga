from unittest.mock import AsyncMock, patch

import pytest

from app.ai.context import build_context
from app.ai.providers.schemas import ToolCall
from app.ai.router import get_gameplay_config
from app.config_loader import load_saga_config
from tests.integration.test_quest_persistence import (
    _create_campaign,
    _openai_provider,
    _reply,
    _script,
    _take_turn,
)


async def test_valid_travel_and_actor_progress_do_not_lose_result_narration(
    auth_client, generation_clients
) -> None:
    campaign = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    captured = _script(
        provider,
        [
            _reply("", ToolCall(id="move", name="move_to", arguments={"location": "Thornhaven"})),
            _reply(
                "",
                ToolCall(
                    id="actor",
                    name="invoke_npc",
                    arguments={"name": "Aldric", "context": "The newcomer asks for help."},
                ),
            ),
            _reply("The elder's reply hangs in the village air."),
        ],
    )
    result = await _take_turn(
        auth_client, campaign["id"], "I go to Thornhaven and ask Aldric for help."
    )
    assert result["npc_dialogues"]
    assert result["narration"] == "The elder's reply hangs in the village air."
    assert len(captured) == 3
    assert (
        "Thornhaven"
        in captured[1]["system_prompt"].split("<character", 1)[1].split("</character>", 1)[0]
    )
    assert (
        "Aldric"
        in captured[1]["system_prompt"]
        .split("<npcs_present>", 1)[1]
        .split("</npcs_present>", 1)[0]
    )


@pytest.mark.parametrize("cap", [1, 3, 8, 17])
async def test_configured_dm_cap_filters_last_step_in_prompt_schema_and_execution(
    auth_client, generation_clients, monkeypatch, cap
):
    monkeypatch.setenv("SAGA_GAMEPLAY_MAX_AGENT_STEPS", str(cap))
    assert get_gameplay_config().max_agent_steps == cap
    campaign = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    responses = [
        _reply(
            "An attempt.",
            ToolCall(id=f"item-{i}", name="add_item", arguments={"name": f"Stone {i}"}),
        )
        for i in range(cap)
    ]
    captured = _script(provider, responses)
    result = await _take_turn(auth_client, campaign["id"])
    assert len(captured) == cap
    assert len(result["character_data"].get("inventory", [])) == cap - 1
    final = captured[-1]
    safe = {"advance_time", "set_scene_mood", "log_event"}
    assert {tool["function"]["name"] for tool in final["tools"]} == safe
    assert "CLOSING STEP" in final["system_prompt"]
    assert 'tool="add_item"' not in final["system_prompt"]


async def test_repeated_rejection_forces_a_close_not_an_extra_call(
    auth_client, generation_clients
):
    campaign = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    captured = _script(
        provider,
        [
            _reply(
                "I try the path.",
                ToolCall(id="bad-1", name="move_to", arguments={"location": "Nowhere"}),
            ),
            _reply(
                "I try it again.",
                ToolCall(id="bad-2", name="move_to", arguments={"location": "Nowhere"}),
            ),
            _reply(
                "The way remains closed.",
                ToolCall(
                    id="bad-3", name="attack", arguments={"attacker": "player", "target": "Lyra"}
                ),
            ),
        ],
    )
    result = await _take_turn(auth_client, campaign["id"])
    assert len(captured) == 3
    assert "CLOSING STEP" in captured[-1]["system_prompt"]
    assert result["world_state"]["npcs"] == campaign["world_state"]["npcs"]


async def test_last_step_can_apply_only_active_terminal_safe_tools(
    auth_client, generation_clients, monkeypatch
):
    monkeypatch.setenv("SAGA_GAMEPLAY_MAX_AGENT_STEPS", "1")
    campaign = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    _script(
        provider,
        [
            _reply(
                "The morning passes.",
                ToolCall(id="time", name="advance_time", arguments={"minutes": 15}),
                ToolCall(id="mood", name="set_scene_mood", arguments={"mood": "peaceful"}),
                ToolCall(
                    id="event",
                    name="log_event",
                    arguments={"description": "A distant bell rings."},
                ),
            )
        ],
    )
    result = await _take_turn(auth_client, campaign["id"])
    assert result["time_passed_minutes"] == 15
    assert result["world_state"]["clock"]["total_minutes"] == 495


async def test_step_prompt_refreshes_mutations_but_loads_history_and_recall_once(
    auth_client, generation_clients
):
    campaign = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    captured = _script(
        provider,
        [
            _reply(
                "An attempt.",
                ToolCall(id="item", name="add_item", arguments={"name": "Lantern"}),
                ToolCall(
                    id="death",
                    name="kill_npc",
                    arguments={"name": "Lyra", "cause": "A narrative death."},
                ),
                ToolCall(
                    id="quest",
                    name="update_quest",
                    arguments={"quest_id": "who_am_i", "status": "completed"},
                ),
            ),
            _reply(
                "You set out.",
                ToolCall(id="move", name="move_to", arguments={"location": "Thornhaven"}),
            ),
            _reply("The village lights appear."),
        ],
    )
    with (
        patch("app.core.dm.dm_nodes.build_context", wraps=build_context) as context,
        patch(
            "app.ai.context._recall_memories",
            new=AsyncMock(return_value=["Remembered checkpoint fact."]),
        ) as recall,
    ):
        await _take_turn(auth_client, campaign["id"])
    assert context.call_count == recall.call_count == 1
    assert (
        "Lantern"
        in captured[1]["system_prompt"].split("<inventory>", 1)[1].split("</inventory>", 1)[0]
    )
    assert '<npc name="Lyra"' not in captured[1]["system_prompt"]
    assert '<quest id="who_am_i"' not in captured[1]["system_prompt"]
    assert '<npc name="Aldric"' in captured[2]["system_prompt"]
    assert all("Remembered checkpoint fact." in call["system_prompt"] for call in captured)


async def test_terminal_step_cannot_invoke_an_actor_or_roll_or_hidden_tool(
    auth_client, generation_clients, monkeypatch
):
    monkeypatch.setenv("SAGA_GAMEPLAY_MAX_AGENT_STEPS", "1")
    campaign = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    captured = _script(
        provider,
        [
            _reply(
                "The scene closes.",
                ToolCall(id="npc", name="invoke_npc", arguments={"name": "Lyra"}),
                ToolCall(
                    id="dice",
                    name="request_dice",
                    arguments={"check": "Stealth", "stat": "DEX", "difficulty": "normal"},
                ),
                ToolCall(id="unknown", name="not_a_tool", arguments={}),
            )
        ],
    )
    result = await _take_turn(auth_client, campaign["id"])
    assert len(captured) == 1
    assert not result["npc_dialogues"] and not result["dice_results"]
    provider.generate.assert_not_called()


async def test_identical_dice_results_stall_but_first_result_is_playable_progress(
    auth_client, generation_clients
):
    campaign = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    args = {"check": "Stealth", "stat": "DEX", "difficulty": "normal"}
    captured = _script(
        provider,
        [
            *[
                _reply(
                    "Different prose cannot mask a reroll.",
                    ToolCall(id=f"roll-{i}", name="request_dice", arguments=args),
                )
                for i in range(3)
            ],
            _reply("The moment is resolved."),
        ],
    )
    with (
        patch("app.core.dice.random.randint", return_value=10),
        patch("app.core.dice.draw_difficulty_modifier", return_value=0),
    ):
        await _take_turn(auth_client, campaign["id"])
    assert len(captured) == 4
    assert "CLOSING STEP" not in captured[2]["system_prompt"]
    assert "CLOSING STEP" in captured[3]["system_prompt"]


async def test_early_completion_does_not_consume_the_dm_budget(auth_client, generation_clients):
    campaign = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    captured = _script(provider, [_reply("A quiet moment.")])
    await _take_turn(auth_client, campaign["id"])
    assert len(captured) == 1


def test_yaml_default_is_eight_and_environment_override_uses_same_path(monkeypatch):
    monkeypatch.delenv("SAGA_GAMEPLAY_MAX_AGENT_STEPS", raising=False)
    assert load_saga_config()["gameplay"]["max_agent_steps"] == 8
    assert get_gameplay_config().max_agent_steps == 8
