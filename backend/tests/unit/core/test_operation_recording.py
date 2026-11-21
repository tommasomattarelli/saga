from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from app.ai.npc_outcomes import NPCSilent
from app.core.dm.dm_tools_executor import tools_node
from app.core.dm.game_state import GameState
from app.core.world_instantiation import instantiate_world
from app.core.world_loader import load_world
from tests.unit.core.test_tools_node import _make_state


def call(tool_name: str, **args: object) -> dict:
    return {"name": tool_name, "args": args, "id": "same", "type": "tool_call"}


async def test_unknown_or_invalid_call_rejects_the_whole_response_before_effects() -> None:
    calls = [
        call("missing"),
        call("request_dice", stat="DEX"),
        call("move_to", location="Nowhere"),
    ]
    state = cast(
        GameState,
        _make_state(messages=[AIMessage(content="", tool_calls=calls)]),
    )
    with pytest.raises(ValueError, match="Tool response rejected before execution"):
        await tools_node(state)
    assert state["world_state"] == {}
    assert state["char_data"] == {}
    assert state.get("operations", []) == []


async def test_domain_rejection_after_valid_effect_is_not_a_static_preflight_failure() -> None:
    result = await tools_node(
        cast(
            GameState,
            _make_state(
                messages=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            call("set_scene_mood", mood="dread_horror"),
                            call("move_to", location="Nowhere"),
                        ],
                    )
                ],
            ),
        )
    )
    assert result["scene_mood"] == "dread_horror"
    assert [record.payload.outcome for record in result["operations"]] == [
        "succeeded",
        "rejected",
    ]
    assert result["operations"][-1].payload.result.reason == "domain_rejection"


async def test_move_executes_before_npc_presence_check() -> None:
    from pathlib import Path

    world_path = Path(__file__).parents[4] / "worlds" / "the-awakening"
    baseline, world_state, _ = instantiate_world(load_world(world_path))
    destination = baseline["slug_map"]["thornhaven"]
    world_state["npcs"]["guard-id"] = {
        "name": "Guard",
        "location": destination,
        "psychology": {},
    }
    state = cast(
        GameState,
        _make_state(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[
                        call("invoke_npc", name="Guard"),
                        call("move_to", location="Thornhaven"),
                    ],
                )
            ],
            world_state=world_state,
            world_baseline=baseline,
            allowed_tools={"move_to", "invoke_npc"},
        ),
    )

    with patch(
        "app.core.dm.npc_beat.invoke_npcs_parallel",
        new=AsyncMock(return_value=[NPCSilent("Guard", ())]),
    ):
        result = await tools_node(state)

    assert result["world_state"]["meta"]["current_location"] == destination
    assert result["operations"][-1].payload.name == "invoke_npc"
    assert result["operations"][-1].payload.outcome == "succeeded"


async def test_operations_accumulate_across_steps_in_execution_order() -> None:
    first = await tools_node(
        cast(
            GameState,
            _make_state(
                messages=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            call("set_scene_mood", mood="neutral"),
                        ],
                    )
                ]
            ),
        )
    )
    second = await tools_node(
        cast(
            GameState,
            _make_state(
                **{
                    **first,
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                call("set_scene_mood", mood="dread_horror"),
                                call(
                                    "request_dice",
                                    stat="DEX",
                                    check="Balance",
                                    difficulty="normal",
                                ),
                            ],
                        )
                    ],
                    "step_count": 2,
                }
            ),
        )
    )
    assert [r.payload.name for r in second["operations"]] == [
        "set_scene_mood",
        "request_dice",
        "set_scene_mood",
    ]
    assert [r.ordinal for r in second["operations"]] == [1, 2, 3]
