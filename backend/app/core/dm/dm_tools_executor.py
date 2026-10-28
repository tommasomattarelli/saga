"""tools_node — executes all tool calls produced by dm_node in a single turn step."""

from __future__ import annotations

import copy
from enum import IntEnum
from typing import Any

import structlog
from langchain_core.messages import ToolMessage
from pydantic import ValidationError

from app.ai.npc_director import invoke_npcs_parallel
from app.ai.router import get_gameplay_config
from app.ai.tools.dm_tools import execute_tool, get_tool
from app.core.dm.dice_results import _handle_dice
from app.core.dm.dm_helpers import get_or_create_segment, sync_narration_to_segment
from app.core.dm.game_state import GameState
from app.core.dm.loop_policy import dm_call_limit, needs_followup, step_tools
from app.core.dm.npc_prehook import validate_or_create_npc
from app.core.dm.npc_results import _handle_npc_results
from app.core.dm.progress import StepProgress
from app.core.npc_fields import resolve_npc_fields
from app.core.psychology import resolve_psychology
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
    from sqlalchemy import select

    from app.core.dm.dm_helpers import last_ai_message, tool_calls_from_ai_message
    from app.dependencies import get_db_context
    from app.models.campaign import Campaign

    ai_msg = last_ai_message(state["messages"])
    if not ai_msg:
        return {}

    tool_calls = _sort_tool_calls(tool_calls_from_ai_message(ai_msg))
    if not tool_calls:
        return {}

    world_state = copy.deepcopy(state["world_state"])
    char_data = copy.deepcopy(state["char_data"])
    quests = state.get("quests") or QuestRegistry()
    progress = StepProgress(world_state, char_data, quests, state.get("progress_fingerprints", []))
    closing = state.get("closing_step", state["step_count"] >= dm_call_limit(state))
    allowed = set(state.get("allowed_tools", step_tools(world_state, closing=closing)))
    tool_events = list(state["tool_events"])
    dice_results = list(state["dice_results"])
    npc_dialogues = list(state["npc_dialogues"])
    called_npcs = list(state["called_npcs"])
    scene_mood = state["scene_mood"]
    time_passed = state["time_passed_minutes"]
    initial_clock = world_state.get("clock", {}).get("total_minutes", 480)
    narration_segments = list(state["narration_segments"])
    step = state["step_count"] - 1  # step_count already incremented by dm_node

    tool_messages: list[ToolMessage] = []

    get_or_create_segment(narration_segments, step)

    for tc in tool_calls:
        name = tc["name"]
        args = tc.get("args", {})
        tc_id = tc.get("id", name)

        if name not in allowed:
            note = (
                "Unknown tool."
                if get_tool(name) is None
                else "This tool is unavailable in this step."
            )
            tool_messages.append(ToolMessage(content=note, tool_call_id=tc_id, name=name))
            continue

        if name in {"request_dice", "invoke_npc"}:
            tool = get_tool(name)
            assert tool is not None
            try:
                args = tool(**args).model_dump(mode="json")
            except ValidationError:
                tool_messages.append(
                    ToolMessage(
                        content="Invalid tool arguments. Check the tool's required fields.",
                        tool_call_id=tc_id,
                        name=name,
                    )
                )
                continue

        if name == "request_dice":
            result_str, roll_data, char_data = _handle_dice(
                args, char_data, step, narration_segments
            )
            dice_results.append({"step": step, "rolls": roll_data})
            progress.record(name, args, roll_data, playable=True)
            tool_messages.append(ToolMessage(content=result_str, tool_call_id=tc_id, name=name))
            continue

        if name == "invoke_npc":
            npc_name = args.get("name", "")
            if npc_name in called_npcs:
                result_str = f"{npc_name} has already spoken this turn."
                tool_messages.append(
                    ToolMessage(content=result_str, tool_call_id=tc_id, name=name)
                )
                continue

            npc_config = get_gameplay_config()
            taxonomy = (state.get("world_baseline") or {}).get("taxonomy")
            ok, error_msg = validate_or_create_npc(
                npc_name,
                world_state,
                npc_config,
                psychology=resolve_psychology(taxonomy),
                npc_fields=resolve_npc_fields(taxonomy),
            )
            if not ok:
                tool_messages.append(ToolMessage(content=error_msg, tool_call_id=tc_id, name=name))
                continue

            called_npcs.append(npc_name)

            async with get_db_context() as db:
                result = await db.execute(
                    select(Campaign).where(Campaign.id == state["campaign_id"])
                )
                campaign = result.scalar_one()

            npc_results = await invoke_npcs_parallel(
                npc_names=[npc_name],
                campaign=campaign,
                player_action=args.get("context", ""),
                dm_narration=state["narration"][-500:] if state["narration"] else "",
            )

            result_str, world_state, char_data = _handle_npc_results(
                npc_name,
                npc_results,
                npc_dialogues,
                narration_segments,
                step,
                world_state,
                char_data,
                baseline=state.get("world_baseline"),
            )
            public = [
                {"npc_name": npc.npc_name, "dialogue": npc.dialogue, "action": npc.action}
                for npc in npc_results
            ]
            usable = any(
                isinstance(entry["dialogue"], str)
                and entry["dialogue"].strip() not in {"", "...", "…"}
                for entry in public
            )
            progress.record(name, args, public, playable=usable)
            tool_messages.append(ToolMessage(content=result_str, tool_call_id=tc_id, name=name))
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

        tool_messages.append(
            ToolMessage(content=tool_result.description, tool_call_id=tc_id, name=name)
        )

    sync_narration_to_segment(narration_segments, step, state["narration"])

    prev_empty = state.get("consecutive_empty_steps", 0)
    consecutive_empty_steps = (
        0 if progress.changed(world_state, char_data, quests) else prev_empty + 1
    )

    return {
        "messages": tool_messages,
        "world_state": world_state,
        "char_data": char_data,
        "quests": quests,
        "tool_events": tool_events,
        "dice_results": dice_results,
        "npc_dialogues": npc_dialogues,
        "called_npcs": called_npcs,
        "scene_mood": scene_mood,
        "time_passed_minutes": time_passed
        + world_state.get("clock", {}).get("total_minutes", initial_clock)
        - initial_clock,
        "narration_segments": narration_segments,
        "consecutive_empty_steps": consecutive_empty_steps,
        "progress_fingerprints": progress.fingerprints,
        "followup_required": needs_followup({tc["name"] for tc in tool_calls}),
    }
