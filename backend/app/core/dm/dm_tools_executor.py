"""tools_node — executes all tool calls produced by dm_node in a single turn step."""

from __future__ import annotations

import copy
from enum import IntEnum
from typing import Any

import structlog
from langchain_core.messages import ToolMessage
from pydantic import ValidationError

from app.ai.tools.dm_tools import execute_tool, get_tool
from app.core.dm.dice_results import _handle_dice
from app.core.dm.dm_helpers import get_or_create_segment
from app.core.dm.game_state import GameState
from app.core.dm.loop_policy import dm_call_limit, needs_followup, step_tools
from app.core.dm.npc_beat import execute_npc_beat
from app.core.dm.operation_recorder import OperationRecorder, capture_state
from app.core.dm.progress import StepProgress
from app.memory.operation_contracts import OperationResult
from app.memory.operation_results import AttackResult, CheckResult, ErrorResult, MessageResult
from app.models.quest import QuestRegistry


class _ToolPriority(IntEnum):
    FIRST = 0  # resolved before others (e.g. request_dice)
    NORMAL = 1
    LAST = 2  # resolved after others (e.g. invoke_npc)


_TOOL_PRIORITY: dict[str, _ToolPriority] = {
    "request_dice": _ToolPriority.FIRST,
    "invoke_npc": _ToolPriority.LAST,
}


def _sort_tool_calls(tool_calls: list[dict]) -> list[dict]:
    return sorted(tool_calls, key=lambda tc: _TOOL_PRIORITY.get(tc["name"], _ToolPriority.NORMAL))


logger = structlog.get_logger()


async def tools_node(state: GameState) -> dict[str, Any]:
    """Execute all tool calls from the last AI message."""
    from app.core.dm.dm_helpers import last_ai_message, tool_calls_from_ai_message

    ai_msg = last_ai_message(state["messages"])
    if not ai_msg:
        return {}

    original_calls = [
        {**call, "_position": index}
        for index, call in enumerate(tool_calls_from_ai_message(ai_msg))
    ]
    tool_calls = _sort_tool_calls(original_calls)
    if not tool_calls:
        return {}

    world_state = copy.deepcopy(state["world_state"])
    char_data = copy.deepcopy(state["char_data"])
    quests = state.get("quests") or QuestRegistry()
    progress = StepProgress(world_state, char_data, quests, state.get("progress_fingerprints", []))
    closing = state.get("closing_step", state["step_count"] >= dm_call_limit(state))
    allowed = set(state.get("allowed_tools", step_tools(world_state, closing=closing)))
    tool_events = list(state["tool_events"])
    operations = OperationRecorder(state.get("operations", []))
    dice_results = list(state["dice_results"])
    npc_beats = list(state.get("npc_beats", []))
    npc_lines = list(state.get("npc_lines", []))
    npc_calls: list[dict] = []
    scene_mood = state["scene_mood"]
    time_passed = state["time_passed_minutes"]
    initial_clock = world_state.get("clock", {}).get("total_minutes", 480)
    narration_segments = list(state["narration_segments"])
    step = state["step_count"] - 1  # step_count already incremented by dm_node

    tool_messages: dict[int, ToolMessage] = {}

    get_or_create_segment(narration_segments, step)

    for tc in tool_calls:
        name = tc["name"]
        args = tc.get("args", {})
        tc_id = tc.get("id", name)
        position = tc["_position"]

        if name not in allowed:
            note = (
                "Unknown tool."
                if get_tool(name) is None
                else "This tool is unavailable in this step."
            )
            tool_messages[position] = ToolMessage(content=note, tool_call_id=tc_id, name=name)
            operations.append(
                origin="npc" if name == "invoke_npc" else "tool",
                name=name,
                arguments=args,
                outcome="rejected",
                step=step,
                result=ErrorResult(
                    description=note,
                    reason="unknown_tool" if get_tool(name) is None else "unavailable",
                ),
            )
            continue

        if name == "invoke_npc":
            npc_calls.append(tc)
            continue

        if name == "request_dice":
            tool = get_tool(name)
            assert tool is not None
            try:
                args = tool(**args).model_dump(mode="json")
            except ValidationError:
                note = "Invalid tool arguments. Check the tool's required fields."
                tool_messages[position] = ToolMessage(
                    content=note,
                    tool_call_id=tc_id,
                    name=name,
                )
                operations.append(
                    origin="tool",
                    name=name,
                    arguments=args,
                    outcome="rejected",
                    step=step,
                    result=ErrorResult(description=note, reason="invalid_arguments"),
                )
                continue

        before = capture_state(world_state, char_data, quests)
        if name == "request_dice":
            result_str, roll_data, char_data = _handle_dice(
                args, char_data, step, narration_segments
            )
            dice_results.append({"step": step, "rolls": roll_data})
            progress.record(name, args, roll_data, playable=True)
            tool_messages[position] = ToolMessage(
                content=result_str, tool_call_id=tc_id, name=name
            )
            operations.append(
                origin="tool",
                name=name,
                arguments=args,
                outcome="succeeded",
                step=step,
                result=CheckResult.model_validate(
                    {"description": result_str, "checks": roll_data}
                ),
                before=before,
                after=capture_state(world_state, char_data, quests),
            )
            continue

        # Regular tools
        tool_result = execute_tool(
            name,
            args,
            world_state,
            char_data,
            baseline=state.get("world_baseline"),
            quests=quests,
        )
        world_state = tool_result.world_state
        char_data = tool_result.char_data
        updated_quests = getattr(tool_result, "quests", None)
        if isinstance(updated_quests, QuestRegistry):
            quests = updated_quests
        operation_result: OperationResult
        if tool_result.outcome != "succeeded":
            operation_result = ErrorResult(
                description=tool_result.description,
                reason=tool_result.error_reason
                or (
                    "domain_rejection" if tool_result.outcome == "rejected" else "execution_failed"
                ),
            )
        elif name == "attack":
            operation_result = AttackResult.model_validate(
                {
                    "description": tool_result.description,
                    **tool_result.extra,
                }
            )
        else:
            operation_result = MessageResult(description=tool_result.description)
        operations.append(
            origin="tool",
            name=name,
            arguments=args,
            outcome=tool_result.outcome,
            result=operation_result,
            step=step,
            before=before,
            after=capture_state(world_state, char_data, quests),
        )
        progress.record(name, args, tool_result.description)

        if name == "set_scene_mood" and tool_result.extra.get("mood"):
            scene_mood = tool_result.extra["mood"]
        tool_cls = get_tool(name)
        if tool_cls and tool_cls.visible():
            tool_events.append(
                {
                    "tool": name,
                    "args": args,
                    "result": tool_result.description,
                    "extra": tool_result.extra,
                }
            )

        tool_messages[position] = ToolMessage(
            content=tool_result.description, tool_call_id=tc_id, name=name
        )

    if npc_calls:
        world_state, char_data, npc_messages = await execute_npc_beat(
            state,
            npc_calls,
            world_state,
            char_data,
            npc_beats,
            npc_lines,
            progress,
        )
        for call, message in zip(npc_calls, npc_messages, strict=True):
            tool_messages[call["_position"]] = message

    prev_empty = state.get("consecutive_empty_steps", 0)
    consecutive_empty_steps = (
        0 if progress.changed(world_state, char_data, quests) else prev_empty + 1
    )

    return {
        "messages": [tool_messages[index] for index in sorted(tool_messages)],
        "world_state": world_state,
        "char_data": char_data,
        "quests": quests,
        "tool_events": tool_events,
        "operations": operations.records,
        "dice_results": dice_results,
        "npc_beats": npc_beats,
        "npc_lines": npc_lines,
        "scene_mood": scene_mood,
        "time_passed_minutes": time_passed
        + world_state.get("clock", {}).get("total_minutes", initial_clock)
        - initial_clock,
        "narration_segments": narration_segments,
        "consecutive_empty_steps": consecutive_empty_steps,
        "progress_fingerprints": progress.fingerprints,
        "followup_required": needs_followup({tc["name"] for tc in tool_calls}),
    }
