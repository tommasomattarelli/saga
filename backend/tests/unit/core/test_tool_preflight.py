from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from app.core.dm.dm_tools_executor import tools_node
from app.core.dm.game_state import GameState
from app.core.dm.tool_preflight import ToolPreflightError
from tests.unit.core.test_tools_node import _make_state


def _call(name: str, args: object, call_id: str) -> dict:
    return {"id": call_id, "name": name, "args": args, "type": "tool_call"}


@pytest.mark.parametrize(
    ("bad_call", "allowed"),
    [
        (_call("set_scene_mood", {"mood": "tense", "extra": "x"}, "bad"), None),
        (_call("set_scene_mood", {"mood": True}, "bad"), None),
        (_call("advance_time", {"minutes": "5"}, "bad"), None),
        (_call("advance_time", {}, "bad"), None),
        (_call("update_npc", {"name": "Guard", "updates": {"condition": 3}}, "bad"), None),
        (_call("not_registered", {}, "bad"), None),
        (_call("set_scene_mood", {"mood": "tense"}, "bad"), {"request_dice"}),
    ],
)
@pytest.mark.asyncio
async def test_invalid_later_call_aborts_entire_response_before_effects(
    bad_call: dict, allowed: set[str] | None
) -> None:
    valid_dice = _call(
        "request_dice",
        {"check": "Stealth", "stat": "DEX", "difficulty": "normal"},
        "dice",
    )
    valid_npc = _call("invoke_npc", {"name": "New NPC"}, "npc")
    state = _make_state(
        messages=[AIMessage(content="", tool_calls=[valid_dice, bad_call, valid_npc])],
        world_state={"npcs": {}},
        char_data={"abilities": {"DEX": 12}},
        allowed_tools=allowed or {"request_dice", "set_scene_mood", "invoke_npc"},
    )
    original_world = state["world_state"].copy()
    original_char = state["char_data"].copy()

    with (
        patch(
            "app.core.dm.dm_tools_executor._handle_dice",
            return_value=("rolled", {}, state["char_data"]),
        ) as handle_dice,
        patch("app.core.dm.dm_tools_executor.execute_tool") as execute_tool,
        patch(
            "app.core.dm.dm_tools_executor.execute_npc_beat",
            new_callable=AsyncMock,
        ) as execute_npc_beat,
        pytest.raises(ToolPreflightError, match="Tool response rejected"),
    ):
        await tools_node(cast(GameState, state))

    handle_dice.assert_not_called()
    execute_tool.assert_not_called()
    execute_npc_beat.assert_not_called()
    assert state["world_state"] == original_world
    assert state["char_data"] == original_char
    assert state.get("operations", []) == []


@pytest.mark.asyncio
async def test_later_invalid_call_blocks_prior_effectful_world_tool() -> None:
    from app.ai.tools.dm_tools import execute_tool

    state = _make_state(
        messages=[
            AIMessage(
                content="",
                tool_calls=[
                    _call("advance_time", {"minutes": 20}, "time"),
                    _call("set_scene_mood", {"mood": "tense", "extra": "invalid"}, "mood"),
                ],
            )
        ],
        world_state={"clock": {"total_minutes": 480}},
        allowed_tools={"advance_time", "set_scene_mood"},
    )
    original_world = state["world_state"].copy()

    with (
        patch("app.core.dm.dm_tools_executor.execute_tool", wraps=execute_tool) as execute,
        pytest.raises(ToolPreflightError, match="Tool response rejected"),
    ):
        await tools_node(cast(GameState, state))

    execute.assert_not_called()
    assert state["world_state"] == original_world
    assert state.get("operations", []) == []


def test_preflight_rejects_non_object_arguments() -> None:
    from app.core.dm.tool_preflight import ToolPreflightError, preflight_tool_calls

    with pytest.raises(ToolPreflightError, match="Tool response rejected") as error:
        preflight_tool_calls([_call("set_scene_mood", ["tense"], "mood")], {"set_scene_mood"})
    assert error.value.diagnostics[0].code.value == "expected_object"
    assert error.value.diagnostics[0].path == ()


def test_preflight_checks_all_calls_without_rewriting_canonical_map_arguments() -> None:
    from app.core.dm.tool_preflight import ToolPreflightError, preflight_tool_calls

    canonical = _call(
        "update_npc",
        {"name": "Guard", "updates": {"condition": "alert"}},
        "update",
    )
    preflight_tool_calls([canonical], {"update_npc"})
    assert canonical["args"] == {"name": "Guard", "updates": {"condition": "alert"}}

    wire_only = _call(
        "update_npc",
        {"name": "Guard", "updates": [{"key": "condition", "value": "alert"}]},
        "wire",
    )
    with pytest.raises(ToolPreflightError) as error:
        preflight_tool_calls(
            [wire_only, _call("advance_time", {"minutes": True}, "time")],
            {"update_npc", "advance_time"},
        )
    assert len(error.value.diagnostics) == 2


@pytest.mark.parametrize(
    ("name", "arguments", "expected"),
    [
        (
            "set_scene_mood",
            {"mood": "tense", "credential-canary": "secret-value"},
            {("unexpected_field", ("<unknown>",))},
        ),
        (
            "set_scene_mood",
            {},
            {("missing", ("mood",))},
        ),
        (
            "advance_time",
            {"minutes": "5"},
            {("expected_integer", ("minutes",))},
        ),
        (
            "update_npc",
            {"name": "Guard"},
            {("missing", ("updates",))},
        ),
        (
            "update_npc",
            {"name": "Guard", "updates": {"private-canary": 3}},
            {("expected_string", ("updates", "<unknown>"))},
        ),
    ],
)
def test_invalid_arguments_expose_only_allowlisted_codes_and_schema_paths(
    name: str, arguments: dict, expected: set[tuple[str, tuple[str | int, ...]]]
) -> None:
    from app.core.dm.tool_preflight import ToolPreflightError, preflight_tool_calls

    with pytest.raises(ToolPreflightError) as error:
        preflight_tool_calls([_call(name, arguments, "bad")], {name})

    actual = {(item.code.value, item.path) for item in error.value.diagnostics}
    assert actual == expected
    assert error.value.diagnostics[0].call_index == 0
    assert "credential-canary" not in str(error.value.diagnostics)
    assert "secret-value" not in str(error.value.diagnostics)
    assert "private-canary" not in str(error.value.diagnostics)


@pytest.mark.parametrize(
    ("name", "allowed", "expected"),
    [
        ("unknown-canary", {"set_scene_mood"}, "tool_not_registered"),
        ("set_scene_mood", set(), "tool_unavailable"),
    ],
)
def test_unknown_and_disallowed_tool_diagnostics_do_not_echo_names(
    name: str, allowed: set[str], expected: str
) -> None:
    from app.core.dm.tool_preflight import ToolPreflightError, preflight_tool_calls

    with pytest.raises(ToolPreflightError) as error:
        preflight_tool_calls([_call(name, {"mood": "tense"}, "tool")], allowed)
    diagnostic = error.value.diagnostics[0]
    assert (diagnostic.call_index, diagnostic.code.value, diagnostic.path) == (0, expected, ())
    assert name not in str(diagnostic)


def test_disallowed_registered_tool_still_has_its_arguments_schema_checked() -> None:
    from app.core.dm.tool_preflight import ToolPreflightError, preflight_tool_calls

    with pytest.raises(ToolPreflightError) as error:
        preflight_tool_calls(
            [_call("set_scene_mood", {"mood": True}, "tool")],
            set(),
        )
    assert [(item.code.value, item.path) for item in error.value.diagnostics] == [
        ("tool_unavailable", ()),
        ("expected_string", ("mood",)),
    ]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_preflight_rejects_non_finite_json_arguments(value: float) -> None:
    from app.core.dm.tool_preflight import ToolPreflightError, preflight_tool_calls

    with pytest.raises(ToolPreflightError) as error:
        preflight_tool_calls(
            [_call("advance_time", {"minutes": value}, "time")],
            {"advance_time"},
        )
    assert [(item.code.value, item.path) for item in error.value.diagnostics] == [
        ("invalid_json", ())
    ]


def test_preflight_accepts_json_enum_strings_and_preserves_arguments() -> None:
    from app.core.dm.tool_preflight import preflight_tool_calls

    calls = [
        _call(
            "request_dice",
            {"check": "Athletics", "stat": "STR", "difficulty": "very_hard"},
            "dice",
        )
    ]
    preflight_tool_calls(calls, {"request_dice"})
    assert calls[0]["args"]["difficulty"] == "very_hard"
