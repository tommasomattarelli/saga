"""tools_node — executes all tool calls produced by dm_node in a single turn step."""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.messages import ToolMessage

from app.ai.npc_director import invoke_npcs_parallel
from app.ai.tools.dm_tools import execute_tool, get_tool
from app.core.combat.combat_graph import combat_graph
from app.core.dice import ability_check
from app.core.dm.game_state import GameState
from app.core.dm.dm_helpers import get_or_create_segment, sync_narration_to_segment
from app.memory.updater import apply_typed_updates

logger = structlog.get_logger()


async def tools_node(state: GameState) -> dict[str, Any]:
    """Execute all tool calls from the last AI message."""
    from sqlalchemy import select

    from app.dependencies import get_db_context
    from app.models.campaign import Campaign
    from app.core.dm.dm_helpers import last_ai_message, tool_calls_from_ai_message

    ai_msg = last_ai_message(state["messages"])
    if not ai_msg:
        return {}

    tool_calls = tool_calls_from_ai_message(ai_msg)
    if not tool_calls:
        return {}

    world_state = dict(state["world_state"])
    char_data = dict(state["char_data"])
    tool_events = list(state["tool_events"])
    dice_results = list(state["dice_results"])
    npc_dialogues = list(state["npc_dialogues"])
    called_npcs = list(state["called_npcs"])
    scene_mood = state["scene_mood"]
    time_passed = state["time_passed_minutes"]
    narration_segments = list(state["narration_segments"])
    step = state["step_count"] - 1  # step_count already incremented by dm_node

    tool_messages: list[ToolMessage] = []

    get_or_create_segment(narration_segments, step)

    for tc in tool_calls:
        name = tc["name"]
        args = tc.get("args", {})
        tc_id = tc.get("id", name)

        if name == "start_combat":
            world_state["_pending_combat_enemies"] = args.get("enemies", [])
            combat_result = await combat_graph.ainvoke(
                {**state, "world_state": world_state, "char_data": char_data}
            )
            world_state = combat_result["world_state"]
            result_str = "Combat initialised. Initiative rolled."
            tool_messages.append(ToolMessage(content=result_str, tool_call_id=tc_id, name=name))
            tool_cls = get_tool(name)
            if tool_cls and tool_cls.visible():
                tool_events.append({
                    "tool": name, "args": args, "result": result_str,
                    "extra": {"combat_state": world_state.get("combat_state", {})},
                })
            continue

        if name == "end_combat":
            world_state["combat_state"] = {
                "active": False, "round": 0,
                "initiative_order": [], "current_turn_index": 0,
            }
            result_str = "Combat ended."
            tool_messages.append(ToolMessage(content=result_str, tool_call_id=tc_id, name=name))
            tool_cls = get_tool(name)
            if tool_cls and tool_cls.visible():
                tool_events.append({"tool": name, "args": args, "result": result_str, "extra": {}})
            continue

        if name == "request_dice":
            result_str, roll_data = _handle_dice(args, char_data, step, narration_segments)
            dice_results.append({"step": step, "rolls": roll_data})
            tool_messages.append(ToolMessage(content=result_str, tool_call_id=tc_id, name=name))
            continue

        if name == "invoke_npc":
            npc_name = args.get("name", "")
            if npc_name in called_npcs:
                result_str = f"{npc_name} has already spoken this turn."
                tool_messages.append(ToolMessage(content=result_str, tool_call_id=tc_id, name=name))
                continue

            called_npcs.append(npc_name)
            npc_profile = world_state.get("npcs", {}).get(npc_name) or {
                "name": npc_name,
                "personality": "neutral",
                "role": "citizen",
            }

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
                npc_name, npc_results, npc_dialogues, narration_segments,
                step, world_state, char_data,
            )
            tool_messages.append(ToolMessage(content=result_str, tool_call_id=tc_id, name=name))
            continue

        # Regular tools
        tool_result = execute_tool(name, args, world_state, char_data)
        world_state = tool_result.world_state
        char_data = tool_result.char_data

        if name == "set_scene_mood" and tool_result.extra.get("mood"):
            scene_mood = tool_result.extra["mood"]
        if name == "advance_time":
            time_passed += args.get("minutes", 0)

        tool_cls = get_tool(name)
        if tool_cls and tool_cls.visible():
            tool_events.append({
                "tool": name, "args": args,
                "result": tool_result.description, "extra": tool_result.extra,
            })

        tool_messages.append(
            ToolMessage(content=tool_result.description, tool_call_id=tc_id, name=name)
        )

    sync_narration_to_segment(narration_segments, step, state["narration"])

    return {
        "messages": tool_messages,
        "world_state": world_state,
        "char_data": char_data,
        "tool_events": tool_events,
        "dice_results": dice_results,
        "npc_dialogues": npc_dialogues,
        "called_npcs": called_npcs,
        "scene_mood": scene_mood,
        "time_passed_minutes": time_passed,
        "narration_segments": narration_segments,
    }


# ── Private helpers ────────────────────────────────────────────────────────────


def _handle_dice(
    args: dict, char_data: dict, step: int, narration_segments: list[dict]
) -> tuple[str, dict]:
    dc = int(args.get("dc", 10))
    stat = args.get("stat", "DEX")
    check = args.get("check") or f"{stat} check"
    reason = args.get("reason", "")

    abilities = char_data.get("abilities", {})
    stat_score = abilities.get(stat, abilities.get(stat.lower(), 10))
    modifier = (stat_score - 10) // 2

    dice_result = ability_check(modifier=modifier, dc=dc)
    roll_obj = dice_result["roll"]
    check_label = check.replace("_", " ").title()

    roll_data = {
        check_label: {
            "expression": roll_obj.expression,
            "rolls": roll_obj.rolls,
            "modifier": roll_obj.modifier,
            "total": roll_obj.total,
            "dc": dc,
            "success": dice_result["success"],
            "outcome": dice_result["outcome"],
            "is_critical": dice_result["is_critical"],
        }
    }

    seg = get_or_create_segment(narration_segments, step)
    seg["dice"] = {**(seg.get("dice") or {}), **roll_data}

    outcome = dice_result.get("outcome", "partial_success")
    result_str = (
        f"{check.title()} check (DC {dc}): rolled {roll_obj.total} "
        f"({modifier:+d} modifier) → {outcome}."
        + (f" Context: {reason}" if reason else "")
    )
    return result_str, roll_data


def _handle_npc_results(
    npc_name: str,
    npc_results: list,
    npc_dialogues: list[dict],
    narration_segments: list[dict],
    step: int,
    world_state: dict,
    char_data: dict,
) -> tuple[str, dict, dict]:
    dialogue_parts: list[str] = []

    for npc in npc_results:
        evt = {"npc_name": npc.npc_name, "dialogue": npc.dialogue, "action": npc.action}
        npc_dialogues.append(evt)

        seg = get_or_create_segment(narration_segments, step)
        seg["npc_dialogues"].append(evt)

        part = f'{npc.npc_name}: "{npc.dialogue}"'
        if npc.action:
            part += f" [{npc.action}]"
        dialogue_parts.append(part)

        npc_ws = world_state.get("npcs", {}).get(npc.npc_name)
        if npc_ws is not None:
            history: list[str] = npc_ws.setdefault("last_interactions", [])
            history.append(f'"{npc.dialogue}"')
            if len(history) > 3:
                history[:] = history[-3:]

        if npc.disposition_change != 0:
            world_state, char_data = apply_typed_updates(
                world_state, char_data,
                [{"key": "npc_disposition", "target": npc.npc_name, "change": npc.disposition_change}],
            )

    result_str = (
        " | ".join(dialogue_parts) if dialogue_parts else f"{npc_name} does not respond."
    )
    return result_str, world_state, char_data
